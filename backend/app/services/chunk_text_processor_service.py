"""Orchestrator for ``POST /api/data-sources/{id}/chunk-completed-text``.

Pulls ``analysis_status='COMPLETED'`` files that already have an
``extracted_text`` body (Step 12 output) and writes character-based
chunks into ``document_chunks``. Embeddings are **not** generated here —
``document_chunks.embedding`` is left ``NULL`` for a follow-up step.

Synchronous routes call :func:`run_chunk_completed_text` (dry-run or
``create_scan_job`` + core). The DB worker runs
:func:`run_chunk_completed_text_core` with an existing ``scan_job_id``.

Per-file transactions: each file's
``DELETE existing chunks → INSERT new chunks`` runs in its own short
transaction that commits before moving to the next file.

**Heartbeat note:** Progress updates run between files. A single very
large ``split_text_into_chunks`` call can block without intermediate
heartbeats; batch-level in-chunk heartbeat is a future improvement.

**Cancel + ``reprocess``:** Cancellation is checked between files. Each
file's delete+insert runs in one DB transaction, so a cancel will not
interrupt mid-transaction. If future code ever splits delete and insert
across transactions, a cancel could theoretically leave a file without
chunks after delete — document that risk if the implementation changes.

Security: nothing here touches credentials, network, or filesystem.
The error summaries that flow into ``scan_failures.error_message`` /
``scan_jobs.error_message`` are short, type-name-based blurbs so server
exception text never reaches persisted columns. Never log full
``chunk_text`` / ``extracted_text``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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
from app.services.data_source_service import DataSourceNotFound
from app.services.document_chunks_service import (
    delete_existing_chunks,
    fetch_completed_for_chunking,
    has_existing_chunks,
    insert_chunks,
)
from app.services.text_extraction_service import parse_include_extensions

_LIMIT_MIN = 0
_LIMIT_MAX = 5000

_SUCCESS_MESSAGE = "Completed text files chunked successfully"
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

_CHUNK_PROGRESS_EVERY = 5
_CANCELLED_MESSAGE = "Job cancelled by request"


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


def _normalize_include_extensions(
    include_extensions: frozenset[str] | str | None,
) -> frozenset[str] | None:
    if include_extensions is None:
        return None
    if isinstance(include_extensions, frozenset):
        return include_extensions
    if isinstance(include_extensions, str):
        s = include_extensions.strip()
        if not s:
            return None
        return parse_include_extensions(s)
    return frozenset(include_extensions)


def _emit_chunk_progress(
    *,
    scan_job_id: UUID | None,
    heartbeat_worker_id: str | None,
    processed: int,
    completed: int,
    failed: int,
    skipped: int,
    current_path: str | None,
) -> None:
    if scan_job_id is None:
        return
    scan_jobs_service.update_scan_job_progress(
        job_id=scan_job_id,
        processed_files=processed,
        completed_files=completed,
        failed_files=failed,
        skipped_files=skipped,
        current_file_path=current_path,
        heartbeat=True,
    )
    if heartbeat_worker_id:
        scan_jobs_service.update_job_heartbeat(scan_job_id, heartbeat_worker_id)


@dataclass(frozen=True)
class ChunkCompletedTextCoreResult:
    """Outcome of :func:`run_chunk_completed_text_core` (sync + worker)."""

    payload: dict[str, Any]
    http_status: int
    finalized_scan_job: bool


def run_chunk_completed_text_core(
    ds_id: UUID,
    *,
    limit: int,
    chunk_size: int,
    chunk_overlap: int,
    min_chunk_size: int,
    reprocess: bool,
    include_extensions: frozenset[str] | str | None,
    scan_job_id: UUID | None,
    requested_by: UUID | None = None,
    cancel_check: Callable[[], bool] | None = None,
    heartbeat_worker_id: str | None = None,
) -> ChunkCompletedTextCoreResult:
    """Chunk COMPLETED files with ``file_contents``. Used by worker with ``scan_job_id``."""
    _ = requested_by

    try:
        _validate_request_params(
            limit=limit,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            min_chunk_size=min_chunk_size,
        )
    except InvalidChunkParameters as exc:
        if scan_job_id is not None:
            scan_jobs_service.fail_scan_job(
                job_id=scan_job_id,
                error_message=str(exc.error)[:4000],
            )
        return ChunkCompletedTextCoreResult(
            payload={
                "status": "error",
                "message": "Invalid chunking parameters",
                "error": exc.error,
            },
            http_status=400,
            finalized_scan_job=bool(scan_job_id),
        )

    try:
        row = datasource_svc.fetch_data_source_row_internal(ds_id=ds_id)
    except DataSourceNotFound:
        if scan_job_id is not None:
            scan_jobs_service.fail_scan_job(
                job_id=scan_job_id,
                error_message="Data source not found",
            )
        return ChunkCompletedTextCoreResult(
            payload=_error_payload(
                message="Data source not found",
                data_source_id=ds_id,
            ),
            http_status=404,
            finalized_scan_job=bool(scan_job_id),
        )

    ds_name = str(row["name"])
    eff_limit = _clamp(int(limit), _LIMIT_MIN, _LIMIT_MAX)
    ext_set = _normalize_include_extensions(include_extensions)

    candidates = fetch_completed_for_chunking(
        ds_id=ds_id,
        limit=eff_limit,
        include_extensions=ext_set,
        reprocess=reprocess,
    )

    def _cancelled() -> bool:
        return bool(cancel_check and cancel_check())

    items: list[dict[str, Any]] = []
    chunked_files_count = 0
    skipped_count = 0
    failed_count = 0
    created_chunks_count = 0

    if scan_job_id is not None:
        _emit_chunk_progress(
            scan_job_id=scan_job_id,
            heartbeat_worker_id=heartbeat_worker_id,
            processed=0,
            completed=0,
            failed=0,
            skipped=0,
            current_path=None,
        )

    if _cancelled() and scan_job_id is not None:
        scan_jobs_service.mark_job_cancelled(
            scan_job_id, message=_CANCELLED_MESSAGE
        )
        return ChunkCompletedTextCoreResult(
            payload={
                "status": "ok",
                "data_source_id": str(ds_id),
                "name": ds_name,
                "scan_job_id": str(scan_job_id),
                "target_count": len(candidates),
                "processed_count": 0,
                "chunked_files_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "created_chunks_count": 0,
                "cancelled": True,
                "dry_run": False,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "message": _CANCELLED_MESSAGE,
                "items": [],
                "warnings": [],
            },
            http_status=200,
            finalized_scan_job=True,
        )

    try:
        with get_db_connection() as conn:
            for idx, frow in enumerate(candidates):
                remote_path = str(frow.get("remote_path") or "")
                if _cancelled() and scan_job_id is not None:
                    scan_jobs_service.mark_job_cancelled(
                        scan_job_id, message=_CANCELLED_MESSAGE
                    )
                    processed_now = (
                        chunked_files_count + skipped_count + failed_count
                    )
                    return ChunkCompletedTextCoreResult(
                        payload={
                            "status": "ok",
                            "data_source_id": str(ds_id),
                            "name": ds_name,
                            "scan_job_id": str(scan_job_id),
                            "target_count": len(candidates),
                            "processed_count": processed_now,
                            "chunked_files_count": chunked_files_count,
                            "skipped_count": skipped_count,
                            "failed_count": failed_count,
                            "created_chunks_count": created_chunks_count,
                            "cancelled": True,
                            "dry_run": False,
                            "chunk_size": chunk_size,
                            "chunk_overlap": chunk_overlap,
                            "message": _CANCELLED_MESSAGE,
                            "items": items,
                            "warnings": [],
                        },
                        http_status=200,
                        finalized_scan_job=True,
                    )

                if scan_job_id is not None:
                    _emit_chunk_progress(
                        scan_job_id=scan_job_id,
                        heartbeat_worker_id=heartbeat_worker_id,
                        processed=chunked_files_count + skipped_count + failed_count,
                        completed=chunked_files_count,
                        failed=failed_count,
                        skipped=skipped_count,
                        current_path=remote_path or None,
                    )

                if _cancelled() and scan_job_id is not None:
                    scan_jobs_service.mark_job_cancelled(
                        scan_job_id, message=_CANCELLED_MESSAGE
                    )
                    processed_now = (
                        chunked_files_count + skipped_count + failed_count
                    )
                    return ChunkCompletedTextCoreResult(
                        payload={
                            "status": "ok",
                            "data_source_id": str(ds_id),
                            "name": ds_name,
                            "scan_job_id": str(scan_job_id),
                            "target_count": len(candidates),
                            "processed_count": processed_now,
                            "chunked_files_count": chunked_files_count,
                            "skipped_count": skipped_count,
                            "failed_count": failed_count,
                            "created_chunks_count": created_chunks_count,
                            "cancelled": True,
                            "dry_run": False,
                            "chunk_size": chunk_size,
                            "chunk_overlap": chunk_overlap,
                            "message": _CANCELLED_MESSAGE,
                            "items": items,
                            "warnings": [],
                        },
                        http_status=200,
                        finalized_scan_job=True,
                    )

                outcome = _process_one_file(
                    conn,
                    ds_id=ds_id,
                    scan_job_id=scan_job_id,
                    row=frow,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    min_chunk_size=min_chunk_size,
                    reprocess=reprocess,
                )
                items.append(outcome["item"])
                kind = outcome["kind"]
                if kind in ("chunked", "reprocessed"):
                    chunked_files_count += 1
                    created_chunks_count += int(outcome.get("created_chunks", 0))
                elif kind == "skipped":
                    skipped_count += 1
                elif kind == "failed":
                    failed_count += 1

                processed_now = chunked_files_count + skipped_count + failed_count
                last_idx = idx == len(candidates) - 1
                if scan_job_id is not None and (
                    last_idx or (idx + 1) % _CHUNK_PROGRESS_EVERY == 0
                ):
                    _emit_chunk_progress(
                        scan_job_id=scan_job_id,
                        heartbeat_worker_id=heartbeat_worker_id,
                        processed=processed_now,
                        completed=chunked_files_count,
                        failed=failed_count,
                        skipped=skipped_count,
                        current_path=remote_path or None,
                    )

                if _cancelled() and scan_job_id is not None:
                    scan_jobs_service.mark_job_cancelled(
                        scan_job_id, message=_CANCELLED_MESSAGE
                    )
                    return ChunkCompletedTextCoreResult(
                        payload={
                            "status": "ok",
                            "data_source_id": str(ds_id),
                            "name": ds_name,
                            "scan_job_id": str(scan_job_id),
                            "target_count": len(candidates),
                            "processed_count": processed_now,
                            "chunked_files_count": chunked_files_count,
                            "skipped_count": skipped_count,
                            "failed_count": failed_count,
                            "created_chunks_count": created_chunks_count,
                            "cancelled": True,
                            "dry_run": False,
                            "chunk_size": chunk_size,
                            "chunk_overlap": chunk_overlap,
                            "message": _CANCELLED_MESSAGE,
                            "items": items,
                            "warnings": [],
                        },
                        http_status=200,
                        finalized_scan_job=True,
                    )
    except Exception as exc:  # pragma: no cover - defensive batch guard
        if scan_job_id is not None:
            scan_jobs_service.fail_scan_job(
                job_id=scan_job_id,
                error_message="Chunk-completed-text batch failed",
            )
        return ChunkCompletedTextCoreResult(
            payload=_error_payload(
                message="Chunk-completed-text batch failed",
                data_source_id=ds_id,
                name=ds_name,
                scan_job_id=scan_job_id,
                error=str(exc),
            ),
            http_status=500,
            finalized_scan_job=bool(scan_job_id),
        )

    target_count = len(candidates)
    processed_count = chunked_files_count + skipped_count + failed_count

    if scan_job_id is not None:
        _emit_chunk_progress(
            scan_job_id=scan_job_id,
            heartbeat_worker_id=heartbeat_worker_id,
            processed=processed_count,
            completed=chunked_files_count,
            failed=failed_count,
            skipped=skipped_count,
            current_path=None,
        )
        scan_jobs_service.complete_scan_job(
            job_id=scan_job_id,
            total_files=target_count,
            processed_files=processed_count,
            completed_files=chunked_files_count,
            failed_files=failed_count,
            skipped_files=skipped_count,
            deleted_files=0,
        )

    return ChunkCompletedTextCoreResult(
        payload={
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
            "message": _SUCCESS_MESSAGE,
            "items": items,
            "warnings": [],
        },
        http_status=200,
        finalized_scan_job=bool(scan_job_id),
    )


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
    requested_by: UUID | None = None,
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

    scan_job_id = scan_jobs_service.create_scan_job(
        ds_id=ds_id,
        job_type=scan_jobs_service.JOB_TYPE_CHUNK_COMPLETED_TEXT,
        requested_by=requested_by,
    )

    core = run_chunk_completed_text_core(
        ds_id,
        limit=eff_limit,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        min_chunk_size=min_chunk_size,
        reprocess=reprocess,
        include_extensions=include_extensions,
        scan_job_id=scan_job_id,
        requested_by=requested_by,
    )
    return core.payload, core.http_status


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
    "ChunkCompletedTextCoreResult",
    "InvalidChunkParameters",
    "run_chunk_completed_text",
    "run_chunk_completed_text_core",
]
