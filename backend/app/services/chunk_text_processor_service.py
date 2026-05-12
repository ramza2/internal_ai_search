"""Orchestrator for ``POST /api/data-sources/{id}/chunk-completed-text``.

Pulls ``analysis_status='COMPLETED'`` files that already have an
``extracted_text`` body (Step 12 output) and writes character-based
chunks into ``document_chunks``. Embeddings are **not** generated here —
``document_chunks.embedding`` is left ``NULL`` for a follow-up step.

Per-file transactions: the orchestrator holds one connection open for
the whole batch, but each file's
``DELETE existing chunks → INSERT new chunks`` runs in its own short
transaction that commits before moving to the next file. A bad file
fails on its own — it does **not** flip ``files.analysis_status`` away
from ``COMPLETED`` since the extraction step already succeeded.

Security: nothing here touches credentials, network, or filesystem.
The error summaries that flow into ``scan_failures.error_message`` /
``scan_jobs.error_message`` are short, type-name-based blurbs so server
exception text never reaches persisted columns.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.db.database import get_db_connection
from app.services import data_source_service as datasource_svc
from app.services import scan_failures_service
from app.services import scan_jobs_service
from app.services.chunking_service import (
    Chunk,
    ChunkingParameterError,
    estimate_chunk_count,
    normalize_text,
    split_text_into_chunks,
    validate_chunk_params,
)
from app.services.document_chunks_service import (
    delete_existing_chunks,
    fetch_completed_for_chunking,
    has_existing_chunks,
    insert_chunks,
)


_LIMIT_MIN = 1
_LIMIT_MAX = 1000

SUCCESS_MESSAGE = "Completed text files chunked successfully"
DRY_RUN_MESSAGE = "Dry run completed. No chunks were stored."

_STATUS_CHUNKED = "CHUNKED"
_STATUS_REPROCESSED = "REPROCESSED"
_STATUS_SKIPPED = "SKIPPED"
_STATUS_FAILED = "FAILED"

_REASON_ALREADY_CHUNKED = "ALREADY_CHUNKED"
_REASON_TEXT_TOO_SHORT = "TEXT_TOO_SHORT"
_REASON_CHUNK_SAVE_FAILED = "CHUNK_SAVE_FAILED"

_PLANNED_CHUNK = "CHUNK"
_PLANNED_SKIP = "SKIP"


class InvalidChunkParameters(Exception):
    """Surfaced by the route layer as ``400 Invalid chunking parameters``."""

    def __init__(self, error: str) -> None:
        super().__init__(error)
        self.error = error


def _clamp(value: int, lo: int, hi: int) -> int:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _error_payload(
    *,
    message: str,
    data_source_id: UUID | None = None,
    name: str | None = None,
    scan_job_id: UUID | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"status": "error", "message": message}
    if data_source_id is not None:
        out["data_source_id"] = str(data_source_id)
    if name is not None:
        out["name"] = name
    if scan_job_id is not None:
        out["scan_job_id"] = str(scan_job_id)
    if error:
        out["error"] = error
    return out


def _make_item_base(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "file_id": str(row.get("file_id")),
        "remote_path": row.get("remote_path"),
        "filename": row.get("filename"),
        "extension": row.get("extension"),
    }


def _validate_request_params(
    *, limit: int, chunk_size: int, chunk_overlap: int, min_chunk_size: int
) -> None:
    if limit < _LIMIT_MIN or limit > _LIMIT_MAX:
        raise InvalidChunkParameters(
            f"limit must be within [{_LIMIT_MIN}, {_LIMIT_MAX}]"
        )
    try:
        validate_chunk_params(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            min_chunk_size=min_chunk_size,
        )
    except ChunkingParameterError as exc:
        raise InvalidChunkParameters(str(exc)) from exc


def run_chunk_completed_text(
    ds_id: UUID,
    *,
    limit: int,
    chunk_size: int,
    chunk_overlap: int,
    min_chunk_size: int,
    reprocess: bool,
    dry_run: bool,
    include_extensions: frozenset[str] | None,
) -> tuple[dict[str, Any], int]:
    """Drive one synchronous batch of COMPLETED-text chunking.

    Returns ``(payload, http_status_code)``. ``DataSourceNotFound`` and
    :class:`InvalidChunkParameters` propagate so the route layer can map
    them to ``404`` / ``400`` respectively.
    """
    _validate_request_params(
        limit=limit,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        min_chunk_size=min_chunk_size,
    )

    row = datasource_svc.fetch_data_source_row_internal(ds_id=ds_id)
    ds_name = row["name"]

    eff_limit = _clamp(int(limit), _LIMIT_MIN, _LIMIT_MAX)

    candidates = fetch_completed_for_chunking(
        ds_id=ds_id,
        limit=eff_limit,
        include_extensions=include_extensions,
        reprocess=reprocess,
    )

    if dry_run:
        return _build_dry_run_payload(
            ds_id=ds_id,
            name=ds_name,
            rows=candidates,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            min_chunk_size=min_chunk_size,
            reprocess=reprocess,
        ), 200

    scan_job_id = scan_jobs_service.create_scan_job(ds_id=ds_id)

    items: list[dict[str, Any]] = []
    chunked_files_count = 0
    skipped_count = 0
    failed_count = 0
    created_chunks_count = 0

    try:
        with get_db_connection() as conn:
            for row in candidates:
                outcome = _process_one_file(
                    conn,
                    ds_id=ds_id,
                    scan_job_id=scan_job_id,
                    row=row,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    min_chunk_size=min_chunk_size,
                    reprocess=reprocess,
                )
                items.append(outcome["item"])
                kind = outcome["kind"]
                if kind in ("chunked", "reprocessed"):
                    chunked_files_count += 1
                    created_chunks_count += int(
                        outcome.get("created_chunks", 0)
                    )
                elif kind == "skipped":
                    skipped_count += 1
                elif kind == "failed":
                    failed_count += 1
    except Exception as exc:  # pragma: no cover - defensive batch guard
        scan_jobs_service.fail_scan_job(
            job_id=scan_job_id,
            error_message="Chunk-completed-text batch failed",
        )
        return (
            _error_payload(
                message="Chunk-completed-text batch failed",
                data_source_id=ds_id,
                name=ds_name,
                scan_job_id=scan_job_id,
                error=str(exc),
            ),
            500,
        )

    target_count = len(candidates)
    processed_count = chunked_files_count + skipped_count + failed_count

    scan_jobs_service.complete_scan_job(
        job_id=scan_job_id,
        total_files=target_count,
        processed_files=processed_count,
        completed_files=chunked_files_count,
        failed_files=failed_count,
        skipped_files=skipped_count,
        deleted_files=0,
    )

    return (
        {
            "status": "ok",
            "data_source_id": str(ds_id),
            "name": ds_name,
            "scan_job_id": str(scan_job_id) if scan_job_id else None,
            "target_count": target_count,
            "processed_count": processed_count,
            "chunked_files_count": chunked_files_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "created_chunks_count": created_chunks_count,
            "dry_run": False,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "message": SUCCESS_MESSAGE,
            "items": items,
            "warnings": [],
        },
        200,
    )


def _build_dry_run_payload(
    *,
    ds_id: UUID,
    name: str,
    rows: list[dict[str, Any]],
    chunk_size: int,
    chunk_overlap: int,
    min_chunk_size: int,
    reprocess: bool,
) -> dict[str, Any]:
    """Per-file planned action without DB writes.

    Uses :func:`estimate_chunk_count` so we don't materialize the chunk
    list just to count it. ``ALREADY_CHUNKED`` only appears with
    ``reprocess=true`` because the candidate query already filters those
    rows out when ``reprocess=false``.
    """
    items: list[dict[str, Any]] = []
    for row in rows:
        base = _make_item_base(row)
        text = row.get("extracted_text") or ""
        normalized = normalize_text(text)
        text_length = len(normalized)
        base["text_length"] = text_length

        if text_length < min_chunk_size:
            base["planned_action"] = _PLANNED_SKIP
            base["reason"] = _REASON_TEXT_TOO_SHORT
            items.append(base)
            continue

        if reprocess and has_existing_chunks(file_id=row["file_id"]):
            base["planned_action"] = _PLANNED_CHUNK
            base["estimated_chunks_count"] = estimate_chunk_count(
                text_length,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            base["reprocess"] = True
            items.append(base)
            continue

        base["planned_action"] = _PLANNED_CHUNK
        base["estimated_chunks_count"] = estimate_chunk_count(
            text_length,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        items.append(base)

    return {
        "status": "ok",
        "data_source_id": str(ds_id),
        "name": name,
        "target_count": len(rows),
        "dry_run": True,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "message": DRY_RUN_MESSAGE,
        "items": items,
    }


def _process_one_file(
    conn,
    *,
    ds_id: UUID,
    scan_job_id: UUID | None,
    row: dict[str, Any],
    chunk_size: int,
    chunk_overlap: int,
    min_chunk_size: int,
    reprocess: bool,
) -> dict[str, Any]:
    """Chunk a single file and commit. Returns a structured outcome."""
    file_id: UUID = row["file_id"]
    remote_path = row.get("remote_path") or ""
    raw_text = row.get("extracted_text") or ""
    normalized = normalize_text(raw_text)
    item = _make_item_base(row)
    item["text_length"] = len(normalized)

    if len(normalized) < min_chunk_size:
        item["status"] = _STATUS_SKIPPED
        item["reason"] = _REASON_TEXT_TOO_SHORT
        return {"kind": "skipped", "item": item}

    try:
        chunks: list[Chunk] = split_text_into_chunks(
            normalized,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            min_chunk_size=min_chunk_size,
        )
    except ChunkingParameterError as exc:
        # Already validated at the route layer, but defend against direct
        # callers: treat as a per-file failure.
        item["status"] = _STATUS_FAILED
        item["reason"] = _REASON_CHUNK_SAVE_FAILED
        scan_failures_service.record_scan_failure(
            scan_job_id=scan_job_id,
            data_source_id=ds_id,
            file_id=file_id,
            remote_path=remote_path,
            error_code=_REASON_CHUNK_SAVE_FAILED,
            error_message=f"ChunkingParameterError: {exc}",
        )
        return {"kind": "failed", "item": item}

    if not chunks:
        # Defensive: ``split_text_into_chunks`` returns ``[]`` only when
        # text is shorter than ``min_chunk_size``, which we already
        # handled above. Treat any other empty-list outcome as a skip.
        item["status"] = _STATUS_SKIPPED
        item["reason"] = _REASON_TEXT_TOO_SHORT
        return {"kind": "skipped", "item": item}

    try:
        if reprocess:
            delete_existing_chunks(conn, file_id=file_id)
        inserted = insert_chunks(
            conn,
            data_source_id=ds_id,
            file_id=file_id,
            chunks=chunks,
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        item["status"] = _STATUS_FAILED
        item["reason"] = _REASON_CHUNK_SAVE_FAILED
        scan_failures_service.record_scan_failure(
            scan_job_id=scan_job_id,
            data_source_id=ds_id,
            file_id=file_id,
            remote_path=remote_path,
            error_code=_REASON_CHUNK_SAVE_FAILED,
            error_message=f"{type(exc).__name__}",
        )
        return {"kind": "failed", "item": item}

    item["status"] = _STATUS_REPROCESSED if reprocess else _STATUS_CHUNKED
    item["chunks_count"] = inserted
    return {
        "kind": "reprocessed" if reprocess else "chunked",
        "item": item,
        "created_chunks": inserted,
    }


__all__ = [
    "InvalidChunkParameters",
    "run_chunk_completed_text",
]
