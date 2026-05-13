"""File / chunk preview from ``file_contents.extracted_text`` (Step 18).

Reads **only** what is already persisted in PostgreSQL — no WebDAV
download, no file mutation. Enforces ``max_chars`` so the response
cannot accidentally ship a multi-megabyte body.

Raises :class:`PreviewError` with ``(status_code, message)`` for every
failure the route layer maps to JSON.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.db.database import get_db_connection
from app.schemas.file_preview import (
    CONTEXT_LINES_MAX,
    CONTEXT_LINES_MIN,
    MAX_CHARS_MAX,
    MAX_CHARS_MIN,
    FilePreviewBody,
    FilePreviewFileMeta,
    FilePreviewOpenInfo,
    FilePreviewSuccessResponse,
    PreviewLineItem,
)
from app.utils.highlight import find_highlights_in_lines
from app.webdav.download import build_file_url


class PreviewError(Exception):
    """Controlled failure surfaced as JSON (never leaks credentials)."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


_FETCH_FILE_SQL = """
    SELECT
        f.id AS file_id,
        f.data_source_id,
        f.filename,
        f.remote_path,
        f.extension,
        f.mime_type,
        f.size_bytes,
        f.analysis_status::text AS analysis_status,
        f.is_directory,
        f.last_modified,
        f.last_indexed_at,
        ds.name AS data_source_name,
        ds.source_type::text AS source_type,
        ds.server_url,
        ds.webdav_root_path,
        ds.is_active
    FROM files AS f
    JOIN data_sources AS ds ON ds.id = f.data_source_id
    WHERE f.id = %s
"""

_FETCH_CONTENT_SQL = """
    SELECT extracted_text, text_length
    FROM file_contents
    WHERE file_id = %s
      AND extracted_text IS NOT NULL
      AND text_length > 0
"""

_FETCH_CHUNK_SQL = """
    SELECT
        id AS chunk_id,
        chunk_index,
        chunk_text,
        start_line,
        end_line
    FROM document_chunks
    WHERE id = %s
      AND file_id = %s
      AND data_source_id = %s
"""


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def _split_lines(text: str) -> list[str]:
    if not text:
        return []
    return text.splitlines()


def _build_numbered_text(rows: list[tuple[int, str]]) -> tuple[str, int]:
    if not rows:
        return "", 0
    parts = [f"{line_no}: {line_text}" for line_no, line_text in rows]
    body = "\n".join(parts)
    return body, len(body)


def _apply_max_chars(
    rows: list[tuple[int, str]], max_chars: int
) -> tuple[list[tuple[int, str]], bool]:
    """Trim ``rows`` from the end until numbered text fits ``max_chars``."""
    if max_chars <= 0:
        return [], True
    cur = list(rows)
    while cur:
        _, char_count = _build_numbered_text(cur)
        if char_count <= max_chars:
            return cur, len(cur) < len(rows)
        cur = cur[:-1]
    return [], True


def _preview_rows_to_response(
    *,
    rows: list[tuple[int, str]],
    max_chars: int,
    context_lines: int,
    mode: str,
    chunk_id: UUID | None,
    chunk_index: int | None,
    preview_start_line: int | None,
    preview_end_line: int | None,
    requested_start_line: int | None,
    requested_end_line: int | None,
    query: str | None,
    file_meta: FilePreviewFileMeta,
) -> FilePreviewSuccessResponse:
    trimmed, tail_trunc = _apply_max_chars(rows, max_chars)
    text, char_count = _build_numbered_text(trimmed)
    highlights = find_highlights_in_lines(trimmed, query)

    body = FilePreviewBody(
        mode=mode,
        chunk_id=chunk_id,
        chunk_index=chunk_index,
        start_line=preview_start_line,
        end_line=preview_end_line,
        requested_start_line=requested_start_line,
        requested_end_line=requested_end_line,
        context_lines=context_lines,
        is_truncated=tail_trunc or (len(trimmed) < len(rows)),
        text=text,
        lines=[PreviewLineItem(line=ln, text=tx) for ln, tx in trimmed],
        line_count=len(trimmed),
        char_count=char_count,
    )
    return FilePreviewSuccessResponse(
        file=file_meta,
        preview=body,
        highlights=highlights,
        message="File preview retrieved successfully",
    )


def _load_file_row(file_id: UUID) -> dict[str, Any]:
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(_FETCH_FILE_SQL, (file_id,))
                row = cur.fetchone()
    except psycopg.Error as exc:
        raise PreviewError(500, f"Database error: {type(exc).__name__}") from exc
    if not row:
        raise PreviewError(404, "File not found")
    if not row.get("is_active"):
        raise PreviewError(404, "Data source not found")
    return dict(row)


def _assert_previewable_file(row: dict[str, Any]) -> None:
    if row.get("is_directory"):
        raise PreviewError(409, "Directory cannot be previewed")
    st = (row.get("analysis_status") or "").upper()
    if st == "DELETED":
        raise PreviewError(409, "File is deleted and cannot be previewed")
    if st == "SKIPPED":
        raise PreviewError(409, "File was skipped and has no preview content")
    if st == "FAILED":
        raise PreviewError(409, "File analysis failed and preview is not available")
    if st == "PENDING":
        raise PreviewError(409, "File has not been processed yet")
    if st != "COMPLETED":
        raise PreviewError(409, "File analysis failed and preview is not available")


def _load_extracted_text(file_id: UUID) -> str:
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(_FETCH_CONTENT_SQL, (file_id,))
                row = cur.fetchone()
    except psycopg.Error as exc:
        raise PreviewError(500, f"Database error: {type(exc).__name__}") from exc
    if not row:
        raise PreviewError(409, "File content is not available")
    text = row.get("extracted_text")
    if not isinstance(text, str) or not text.strip():
        raise PreviewError(409, "File content is not available")
    tl = int(row.get("text_length") or len(text))
    if tl <= 0:
        raise PreviewError(409, "File content is not available")
    return text


def _load_chunk(
    *, chunk_id: UUID, file_id: UUID, data_source_id: UUID
) -> dict[str, Any]:
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(_FETCH_CHUNK_SQL, (chunk_id, file_id, data_source_id))
                row = cur.fetchone()
    except psycopg.Error as exc:
        raise PreviewError(500, f"Database error: {type(exc).__name__}") from exc
    if not row:
        raise PreviewError(404, "Chunk not found in file")
    return dict(row)


def _make_open_info(row: dict[str, Any]) -> FilePreviewOpenInfo:
    ds_id = row["data_source_id"]
    server = (row.get("server_url") or "").strip()
    root = row.get("webdav_root_path")
    root_s = (
        root.strip()
        if isinstance(root, str)
        else ("" if root is None else str(root).strip())
    )
    remote = (row.get("remote_path") or "/").strip()
    if not remote.startswith("/"):
        remote = "/" + remote
    webdav_url = build_file_url(
        server_url=server,
        webdav_root_path=root_s,
        remote_path=remote,
    )
    return FilePreviewOpenInfo(
        data_source_id=ds_id,
        server_url=server,
        webdav_root_path=root_s or None,
        remote_path=remote,
        webdav_url=webdav_url,
    )


def _make_file_meta(row: dict[str, Any]) -> FilePreviewFileMeta:
    return FilePreviewFileMeta(
        file_id=row["file_id"],
        data_source_id=row["data_source_id"],
        data_source_name=str(row.get("data_source_name") or ""),
        source_type=str(row.get("source_type") or ""),
        filename=row.get("filename"),
        remote_path=row.get("remote_path"),
        extension=row.get("extension"),
        mime_type=row.get("mime_type"),
        size_bytes=row.get("size_bytes"),
        analysis_status=str(row.get("analysis_status") or ""),
        last_modified=row.get("last_modified"),
        last_indexed_at=row.get("last_indexed_at"),
        open_info=_make_open_info(row),
    )


def _head_rows_greedy(all_lines: list[str], max_chars: int) -> list[tuple[int, str]]:
    """From line 1, add whole lines until the numbered preview exceeds ``max_chars``."""
    n_lines = len(all_lines)
    if n_lines == 0:
        return [(1, "")]
    rows: list[tuple[int, str]] = []
    for i in range(n_lines):
        candidate = rows + [(i + 1, all_lines[i])]
        _, cc = _build_numbered_text(candidate)
        if cc <= max_chars:
            rows = candidate
            continue
        if not rows:
            prefix_len = len(f"{i + 1}: ")
            keep = max(0, max_chars - prefix_len)
            rows = [(i + 1, all_lines[i][:keep])]
        break
    return rows


def run_file_preview(
    *,
    file_id: UUID,
    chunk_id: UUID | None,
    start_line: int | None,
    end_line: int | None,
    context_lines: int,
    max_chars: int,
    query: str | None,
    include_full_text: bool,
) -> FilePreviewSuccessResponse:
    """Core handler for ``GET /api/files/{file_id}/preview``."""
    ctx = _clamp_int(context_lines, CONTEXT_LINES_MIN, CONTEXT_LINES_MAX)
    mc = _clamp_int(max_chars, MAX_CHARS_MIN, MAX_CHARS_MAX)

    frow = _load_file_row(file_id)
    _assert_previewable_file(frow)
    file_meta = _make_file_meta(frow)
    data_source_id: UUID = frow["data_source_id"]

    full_text = _load_extracted_text(file_id)
    all_lines = _split_lines(full_text)
    if not all_lines:
        all_lines = [""]
    n_lines = len(all_lines)

    # chunk_id wins over explicit line query params
    if chunk_id is not None:
        ch = _load_chunk(chunk_id=chunk_id, file_id=file_id, data_source_id=data_source_id)
        sl = ch.get("start_line")
        el = ch.get("end_line")
        cidx = ch.get("chunk_index")
        ctext = ch.get("chunk_text") or ""

        if sl is not None and el is not None:
            try:
                rs = int(sl)
                re = int(el)
            except (TypeError, ValueError) as exc:
                raise PreviewError(400, "Invalid chunk line range") from exc
            if re < rs:
                raise PreviewError(
                    400, "end_line must be greater than or equal to start_line"
                )
            rs = max(1, min(rs, n_lines))
            re = max(1, min(re, n_lines))
            if re < rs:
                raise PreviewError(
                    400, "end_line must be greater than or equal to start_line"
                )
            ps = max(1, rs - ctx)
            pe = min(n_lines, re + ctx)
            rows = [(i + 1, all_lines[i]) for i in range(ps - 1, pe)]
            return _preview_rows_to_response(
                rows=rows,
                max_chars=mc,
                context_lines=ctx,
                mode="chunk",
                chunk_id=chunk_id,
                chunk_index=int(cidx) if cidx is not None else None,
                preview_start_line=ps,
                preview_end_line=pe,
                requested_start_line=rs,
                requested_end_line=re,
                query=query,
                file_meta=file_meta,
            )

        chunk_lines = _split_lines(ctext) if ctext else [""]
        rows_ct = [(i + 1, chunk_lines[i]) for i in range(len(chunk_lines))]
        trimmed, tail_trunc = _apply_max_chars(rows_ct, mc)
        text, char_count = _build_numbered_text(trimmed)
        highlights = find_highlights_in_lines(trimmed, query)
        body = FilePreviewBody(
            mode="chunk_text_only",
            chunk_id=chunk_id,
            chunk_index=int(cidx) if cidx is not None else None,
            start_line=None,
            end_line=None,
            requested_start_line=None,
            requested_end_line=None,
            context_lines=ctx,
            is_truncated=tail_trunc or (len(trimmed) < len(rows_ct)),
            text=text,
            lines=[PreviewLineItem(line=ln, text=tx) for ln, tx in trimmed],
            line_count=len(trimmed),
            char_count=char_count,
        )
        return FilePreviewSuccessResponse(
            file=file_meta,
            preview=body,
            highlights=highlights,
            message="File preview retrieved successfully",
        )

    if start_line is not None or end_line is not None:
        if start_line is not None and end_line is not None:
            rs = max(1, int(start_line))
            re = int(end_line)
            if re < rs:
                raise PreviewError(
                    400, "end_line must be greater than or equal to start_line"
                )
            rs = max(1, min(rs, n_lines))
            re = max(1, min(re, n_lines))
            if re < rs:
                raise PreviewError(
                    400, "end_line must be greater than or equal to start_line"
                )
        elif end_line is not None:
            re = max(1, min(int(end_line), n_lines))
            rs = max(1, re - ctx)
        else:
            assert start_line is not None
            rs = max(1, min(int(start_line), n_lines))
            re = min(n_lines, rs + ctx * 2)

        ps = max(1, rs - ctx)
        pe = min(n_lines, re + ctx)
        rows_lr = [(i + 1, all_lines[i]) for i in range(ps - 1, pe)]
        return _preview_rows_to_response(
            rows=rows_lr,
            max_chars=mc,
            context_lines=ctx,
            mode="lines",
            chunk_id=None,
            chunk_index=None,
            preview_start_line=ps,
            preview_end_line=pe,
            requested_start_line=rs,
            requested_end_line=re,
            query=query,
            file_meta=file_meta,
        )

    if include_full_text:
        rows_hd = [(i + 1, all_lines[i]) for i in range(n_lines)]
        trimmed, tail_trunc = _apply_max_chars(rows_hd, mc)
        text, char_count = _build_numbered_text(trimmed)
        highlights = find_highlights_in_lines(trimmed, query)
        ps = trimmed[0][0] if trimmed else 1
        pe = trimmed[-1][0] if trimmed else 1
        body = FilePreviewBody(
            mode="head",
            chunk_id=None,
            chunk_index=None,
            start_line=ps,
            end_line=pe,
            requested_start_line=1,
            requested_end_line=n_lines,
            context_lines=ctx,
            is_truncated=tail_trunc or (len(trimmed) < n_lines),
            text=text,
            lines=[PreviewLineItem(line=ln, text=tx) for ln, tx in trimmed],
            line_count=len(trimmed),
            char_count=char_count,
        )
        return FilePreviewSuccessResponse(
            file=file_meta,
            preview=body,
            highlights=highlights,
            message="File preview retrieved successfully",
        )

    rows_hd = _head_rows_greedy(all_lines, mc)
    trimmed, tail_trunc = _apply_max_chars(rows_hd, mc)
    text, char_count = _build_numbered_text(trimmed)
    highlights = find_highlights_in_lines(trimmed, query)
    ps = trimmed[0][0] if trimmed else 1
    pe = trimmed[-1][0] if trimmed else 1
    body = FilePreviewBody(
        mode="head",
        chunk_id=None,
        chunk_index=None,
        start_line=ps,
        end_line=pe,
        requested_start_line=ps,
        requested_end_line=pe,
        context_lines=ctx,
        is_truncated=tail_trunc or (len(trimmed) < len(rows_hd)),
        text=text,
        lines=[PreviewLineItem(line=ln, text=tx) for ln, tx in trimmed],
        line_count=len(trimmed),
        char_count=char_count,
    )
    return FilePreviewSuccessResponse(
        file=file_meta,
        preview=body,
        highlights=highlights,
        message="File preview retrieved successfully",
    )


def run_chunk_preview(
    *,
    file_id: UUID,
    chunk_id: UUID,
    context_lines: int,
    max_chars: int,
    query: str | None,
) -> FilePreviewSuccessResponse:
    """Alias for ``run_file_preview(..., chunk_id=chunk_id, ...)``."""
    return run_file_preview(
        file_id=file_id,
        chunk_id=chunk_id,
        start_line=None,
        end_line=None,
        context_lines=context_lines,
        max_chars=max_chars,
        query=query,
        include_full_text=False,
    )


__all__ = [
    "PreviewError",
    "run_chunk_preview",
    "run_file_preview",
]
