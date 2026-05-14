"""Orchestrator for ``POST /api/data-sources/{id}/embed-pending-chunks``.

Pulls ``document_chunks`` rows whose ``embedding IS NULL`` (or every
COMPLETED chunk when ``reembed=true``), generates 1024-D vectors via the
configured Ollama embedding model, and writes them back to
``document_chunks.embedding vector(1024)`` using parameter-bound
``%s::vector`` casts. Once a file's chunks are all embedded the
orchestrator flips ``files.last_indexed_at = NOW()`` — that bump is the
project's "ready for search" signal and is the *only* place in the
codebase that sets ``last_indexed_at``.

Synchronous routes call :func:`run_embed_pending_chunks` (dry-run or
``create_scan_job`` + :func:`run_embed_pending_chunks_core`). The DB
worker runs :func:`run_embed_pending_chunks_core` with an existing
``scan_job_id`` (no duplicate ``create_scan_job``).

**scan_jobs counters:** Column names say ``*_files`` but for this job
``processed_files`` / ``completed_files`` / ``failed_files`` /
``skipped_files`` are updated as **chunk** counts (see README).

**Heartbeat:** Emits at job start, before each embedding batch (Ollama
call), and after each batch commits. A single batch can still run long
if Ollama is slow — intra-batch heartbeat is a possible future
improvement.

**Cancel:** Checked before each batch and after each batch at DB-safe
boundaries. ``reembed=true`` + cancel mid-run can leave **some** chunks
with new vectors and others with old — not atomic across the whole
source; a future version column / two-phase swap could address this.

Security: never log ``chunk_text`` or embedding vectors; error strings
are type-name / short API blurbs only.
"""

from __future__ import annotations

from collections import defaultdict, OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg

from app.core.config import Settings
from app.db.database import get_db_connection
from app.embedding.ollama_embedding_client import (
    BatchEmbeddingResult,
    create_embeddings_batch,
)
from app.services import data_source_service as datasource_svc
from app.services import embedding_models_service
from app.services import scan_jobs_service
from app.services.chunk_embedding_repository import (
    fetch_file_for_ownership_check,
    fetch_pending_chunks_for_embedding,
    maybe_mark_file_indexed,
    update_chunk_embedding,
)
from app.services.text_extraction_service import parse_include_extensions

_LIMIT_MIN = 1
_LIMIT_MAX = 10_000
_BATCH_MIN = 1
_BATCH_MAX = 128

_REASON_EMBEDDING_DIMENSION_MISMATCH = "EMBEDDING_DIMENSION_MISMATCH"
_REASON_EMBEDDING_API_FAILED = "EMBEDDING_API_FAILED"
_REASON_DB_UPDATE_FAILED = "DB_UPDATE_FAILED"

_STATUS_EMBEDDED = "EMBEDDED"
_STATUS_FAILED = "FAILED"

SUCCESS_MESSAGE = "Pending chunks embedded successfully"
DRY_RUN_MESSAGE = "Dry run completed. No embeddings were generated or stored."
NO_CANDIDATES_MESSAGE = "No chunks to embed"
_CANCELLED_MESSAGE = "Job cancelled by request"


class FileNotInDataSource(Exception):
    """Surfaced by the route layer as ``404 File not found in data source``."""


def _clamp(value: int, lo: int, hi: int) -> int:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _normalize_include_extensions(
    include_extensions: frozenset[str] | str | None,
) -> frozenset[str] | None:
    if include_extensions is None:
        return None
    if isinstance(include_extensions, frozenset):
        return include_extensions if include_extensions else None
    s = str(include_extensions).strip()
    if not s:
        return None
    return parse_include_extensions(s)


def _emit_embed_progress(
    *,
    scan_job_id: UUID | None,
    heartbeat_worker_id: str | None,
    processed_chunks: int,
    embedded_chunks: int,
    failed_chunks: int,
    skipped_chunks: int,
    current_path: str | None,
) -> None:
    if scan_job_id is None:
        return
    scan_jobs_service.update_scan_job_progress(
        job_id=scan_job_id,
        processed_files=processed_chunks,
        completed_files=embedded_chunks,
        failed_files=failed_chunks,
        skipped_files=skipped_chunks,
        deleted_files=0,
        current_file_path=current_path,
        heartbeat=True,
    )
    if heartbeat_worker_id:
        scan_jobs_service.update_job_heartbeat(scan_job_id, heartbeat_worker_id)


def _error_payload(
    *,
    message: str,
    data_source_id: UUID | None = None,
    scan_job_id: UUID | None = None,
    embedding_model: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"status": "error", "message": message}
    if data_source_id is not None:
        out["data_source_id"] = str(data_source_id)
    if scan_job_id is not None:
        out["scan_job_id"] = str(scan_job_id)
    if embedding_model is not None:
        out["embedding_model"] = embedding_model
    if error:
        out["error"] = error
    return out


def _group_rows_by_file(rows: list[dict[str, Any]]) -> "OrderedDict[UUID, dict[str, Any]]":
    grouped: "OrderedDict[UUID, dict[str, Any]]" = OrderedDict()
    for r in rows:
        fid: UUID = r["file_id"]
        bucket = grouped.get(fid)
        if bucket is None:
            grouped[fid] = {
                "file_id": fid,
                "remote_path": r.get("remote_path"),
                "filename": r.get("filename"),
                "extension": r.get("extension"),
                "chunks": [r],
            }
        else:
            bucket["chunks"].append(r)
    return grouped


def _build_dry_run_payload(
    *,
    ds_id: UUID,
    name: str,
    rows: list[dict[str, Any]],
    batch_size: int,
    embedding_model: str,
    embedding_provider: str,
    expected_dimension: int,
) -> dict[str, Any]:
    grouped = _group_rows_by_file(rows)
    items: list[dict[str, Any]] = []
    for bucket in grouped.values():
        items.append(
            {
                "file_id": str(bucket["file_id"]),
                "remote_path": bucket["remote_path"],
                "filename": bucket["filename"],
                "target_chunks": len(bucket["chunks"]),
            }
        )

    target_count = len(rows)
    estimated_batches = (
        (target_count + batch_size - 1) // batch_size if target_count else 0
    )

    return {
        "status": "ok",
        "data_source_id": str(ds_id),
        "name": name,
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "expected_dimension": expected_dimension,
        "target_chunks_count": target_count,
        "estimated_batches": estimated_batches,
        "affected_files_count": len(grouped),
        "batch_size": batch_size,
        "dry_run": True,
        "message": DRY_RUN_MESSAGE,
        "items": items,
    }


def _empty_ok_payload(
    *,
    ds_id: UUID,
    ds_name: str,
    scan_job_id: UUID | None,
    embedding_provider: str,
    embedding_model: str,
    expected_dimension: int,
    eff_batch: int,
) -> dict[str, Any]:
    return {
        "status": "ok",
        "data_source_id": str(ds_id),
        "name": ds_name,
        "scan_job_id": str(scan_job_id) if scan_job_id else None,
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "expected_dimension": expected_dimension,
        "target_chunks_count": 0,
        "processed_chunks_count": 0,
        "embedded_chunks_count": 0,
        "failed_chunks_count": 0,
        "affected_files_count": 0,
        "completed_files_count": 0,
        "batch_size": eff_batch,
        "dry_run": False,
        "message": NO_CANDIDATES_MESSAGE,
        "items": [],
        "warnings": [],
    }


def _cancelled_payload(
    *,
    ds_id: UUID,
    ds_name: str,
    scan_job_id: UUID,
    embedding_provider: str,
    embedding_model: str,
    expected_dimension: int,
    target_count: int,
    eff_batch: int,
    embedded_count: int,
    failed_count: int,
    per_file_outcomes: "OrderedDict[UUID, dict[str, Any]]",
    failure_items: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    processed = embedded_count + failed_count
    completed_files = sum(
        1 for o in per_file_outcomes.values() if o["file_index_completed"]
    )
    return {
        "status": "ok",
        "data_source_id": str(ds_id),
        "name": ds_name,
        "scan_job_id": str(scan_job_id),
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "expected_dimension": expected_dimension,
        "target_chunks_count": target_count,
        "processed_chunks_count": processed,
        "embedded_chunks_count": embedded_count,
        "failed_chunks_count": failed_count,
        "affected_files_count": len(per_file_outcomes),
        "completed_files_count": completed_files,
        "batch_size": eff_batch,
        "dry_run": False,
        "cancelled": True,
        "message": _CANCELLED_MESSAGE,
        "items": list(per_file_outcomes.values()),
        "failures": failure_items,
        "warnings": warnings,
    }


@dataclass(frozen=True)
class EmbedPendingChunksCoreResult:
    """Outcome of :func:`run_embed_pending_chunks_core` (sync + worker)."""

    payload: dict[str, Any]
    http_status: int
    finalized_scan_job: bool


def run_embed_pending_chunks_core(
    settings: Settings,
    ds_id: UUID,
    *,
    ds_name: str | None,
    rows: list[dict[str, Any]] | None,
    limit: int,
    batch_size: int,
    include_extensions: frozenset[str] | str | None,
    reembed: bool,
    file_id: UUID | None,
    scan_job_id: UUID | None,
    requested_by: UUID | None = None,
    cancel_check: Callable[[], bool] | None = None,
    heartbeat_worker_id: str | None = None,
) -> EmbedPendingChunksCoreResult:
    """Execute embedding for pre-fetched rows (sync) or fetch inside (worker).

    When ``scan_job_id`` is set, this function finalizes the scan job
    (complete / fail / cancel) and returns ``finalized_scan_job=True``.
    """
    _ = requested_by  # reserved for future audit hooks
    eff_limit = _clamp(int(limit), _LIMIT_MIN, _LIMIT_MAX)
    eff_batch = _clamp(int(batch_size), _BATCH_MIN, _BATCH_MAX)
    ext_set = _normalize_include_extensions(include_extensions)

    if ds_name is None:
        ds_row = datasource_svc.fetch_data_source_row_internal(ds_id=ds_id)
        ds_name = str(ds_row["name"])

    if file_id is not None:
        owner = fetch_file_for_ownership_check(file_id=file_id)
        if not owner or owner.get("data_source_id") != ds_id:
            raise FileNotInDataSource(
                f"file_id={file_id} does not belong to data_source_id={ds_id}"
            )

    embedding_provider = settings.embedding_provider
    embedding_model = settings.embedding_model
    expected_dimension = int(settings.embedding_dimension)

    if rows is None:
        rows = fetch_pending_chunks_for_embedding(
            ds_id=ds_id,
            limit=eff_limit,
            include_extensions=ext_set,
            file_id=file_id,
            reembed=reembed,
        )

    if not rows:
        if scan_job_id is not None:
            scan_jobs_service.complete_scan_job(
                job_id=scan_job_id,
                total_files=0,
                processed_files=0,
                completed_files=0,
                failed_files=0,
                skipped_files=0,
                deleted_files=0,
            )
            return EmbedPendingChunksCoreResult(
                payload=_empty_ok_payload(
                    ds_id=ds_id,
                    ds_name=ds_name,
                    scan_job_id=scan_job_id,
                    embedding_provider=embedding_provider,
                    embedding_model=embedding_model,
                    expected_dimension=expected_dimension,
                    eff_batch=eff_batch,
                ),
                http_status=200,
                finalized_scan_job=True,
            )
        return EmbedPendingChunksCoreResult(
            payload=_empty_ok_payload(
                ds_id=ds_id,
                ds_name=ds_name,
                scan_job_id=None,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                expected_dimension=expected_dimension,
                eff_batch=eff_batch,
            ),
            http_status=200,
            finalized_scan_job=False,
        )

    embedding_model_id = embedding_models_service.ensure_embedding_model_registered(
        provider=embedding_provider,
        model=embedding_model,
        dimension=expected_dimension,
    )
    has_model_col = embedding_models_service.column_exists(
        table="document_chunks", column="embedding_model_id"
    )

    def _cancelled() -> bool:
        return bool(cancel_check and cancel_check())

    target_count = len(rows)
    embedded_count = 0
    failed_count = 0
    warnings: list[str] = []
    per_file_outcomes: "OrderedDict[UUID, dict[str, Any]]" = OrderedDict()
    failure_items: list[dict[str, Any]] = []

    grouped = _group_rows_by_file(rows)
    for fid, bucket in grouped.items():
        per_file_outcomes[fid] = {
            "file_id": str(fid),
            "remote_path": bucket["remote_path"],
            "filename": bucket["filename"],
            "total_chunks": len(bucket["chunks"]),
            "embedded_chunks": 0,
            "failed_chunks": 0,
            "file_index_completed": False,
        }

    if scan_job_id is not None:
        first_path = str(rows[0].get("remote_path") or "") if rows else None
        _emit_embed_progress(
            scan_job_id=scan_job_id,
            heartbeat_worker_id=heartbeat_worker_id,
            processed_chunks=0,
            embedded_chunks=0,
            failed_chunks=0,
            skipped_chunks=0,
            current_path=first_path or None,
        )

    if _cancelled() and scan_job_id is not None:
        scan_jobs_service.mark_job_cancelled(scan_job_id, message=_CANCELLED_MESSAGE)
        return EmbedPendingChunksCoreResult(
            payload=_cancelled_payload(
                ds_id=ds_id,
                ds_name=ds_name,
                scan_job_id=scan_job_id,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                expected_dimension=expected_dimension,
                target_count=target_count,
                eff_batch=eff_batch,
                embedded_count=0,
                failed_count=0,
                per_file_outcomes=per_file_outcomes,
                failure_items=failure_items,
                warnings=warnings,
            ),
            http_status=200,
            finalized_scan_job=True,
        )

    try:
        with get_db_connection() as conn:
            for start in range(0, target_count, eff_batch):
                if _cancelled() and scan_job_id is not None:
                    scan_jobs_service.mark_job_cancelled(
                        scan_job_id, message=_CANCELLED_MESSAGE
                    )
                    return EmbedPendingChunksCoreResult(
                        payload=_cancelled_payload(
                            ds_id=ds_id,
                            ds_name=ds_name,
                            scan_job_id=scan_job_id,
                            embedding_provider=embedding_provider,
                            embedding_model=embedding_model,
                            expected_dimension=expected_dimension,
                            target_count=target_count,
                            eff_batch=eff_batch,
                            embedded_count=embedded_count,
                            failed_count=failed_count,
                            per_file_outcomes=per_file_outcomes,
                            failure_items=failure_items,
                            warnings=warnings,
                        ),
                        http_status=200,
                        finalized_scan_job=True,
                    )

                end = min(start + eff_batch, target_count)
                batch = rows[start:end]
                cur_path = str(batch[0].get("remote_path") or "") if batch else None
                if scan_job_id is not None:
                    _emit_embed_progress(
                        scan_job_id=scan_job_id,
                        heartbeat_worker_id=heartbeat_worker_id,
                        processed_chunks=embedded_count + failed_count,
                        embedded_chunks=embedded_count,
                        failed_chunks=failed_count,
                        skipped_chunks=0,
                        current_path=cur_path or None,
                    )

                texts = [r["chunk_text"] for r in batch]

                api_result: BatchEmbeddingResult = create_embeddings_batch(
                    base_url=settings.ollama_base_url,
                    model=embedding_model,
                    texts=texts,
                    timeout_seconds=settings.embedding_timeout_seconds,
                )

                if not api_result.success and api_result.error and all(
                    v is None for v in api_result.vectors
                ):
                    if scan_job_id is not None:
                        scan_jobs_service.fail_scan_job(
                            job_id=scan_job_id,
                            error_message=api_result.error,
                        )
                    return EmbedPendingChunksCoreResult(
                        payload=_error_payload(
                            message="Failed to generate embeddings",
                            data_source_id=ds_id,
                            scan_job_id=scan_job_id,
                            embedding_model=embedding_model,
                            error=api_result.error,
                        ),
                        http_status=502,
                        finalized_scan_job=bool(scan_job_id),
                    )

                pending_embedded: list[tuple[UUID, UUID]] = []
                pending_failures: list[dict[str, Any]] = []
                files_touched: set[UUID] = set()

                try:
                    with conn.transaction():
                        for i, row in enumerate(batch):
                            chunk_id: UUID = row["chunk_id"]
                            fid_local: UUID = row["file_id"]

                            vec = api_result.vectors[i]
                            per_err = api_result.per_text_errors[i]

                            if vec is None:
                                pending_failures.append(
                                    {
                                        "chunk_id": str(chunk_id),
                                        "file_id": str(fid_local),
                                        "remote_path": row.get("remote_path"),
                                        "status": _STATUS_FAILED,
                                        "reason": _REASON_EMBEDDING_API_FAILED,
                                        "error": per_err or "Unknown embedding error",
                                    }
                                )
                                continue

                            if len(vec) != expected_dimension:
                                pending_failures.append(
                                    {
                                        "chunk_id": str(chunk_id),
                                        "file_id": str(fid_local),
                                        "remote_path": row.get("remote_path"),
                                        "status": _STATUS_FAILED,
                                        "reason": _REASON_EMBEDDING_DIMENSION_MISMATCH,
                                        "expected_dimension": expected_dimension,
                                        "actual_dimension": len(vec),
                                    }
                                )
                                continue

                            try:
                                with conn.transaction():
                                    update_chunk_embedding(
                                        conn,
                                        chunk_id=chunk_id,
                                        vector=vec,
                                        embedding_model_id=embedding_model_id,
                                        has_embedding_model_id_column=has_model_col,
                                    )
                            except psycopg.Error as db_exc:
                                pending_failures.append(
                                    {
                                        "chunk_id": str(chunk_id),
                                        "file_id": str(fid_local),
                                        "remote_path": row.get("remote_path"),
                                        "status": _STATUS_FAILED,
                                        "reason": _REASON_DB_UPDATE_FAILED,
                                        "error": type(db_exc).__name__,
                                    }
                                )
                                continue

                            pending_embedded.append((chunk_id, fid_local))
                            files_touched.add(fid_local)

                except psycopg.Error as batch_exc:
                    for row in batch:
                        pending_failures.append(
                            {
                                "chunk_id": str(row["chunk_id"]),
                                "file_id": str(row["file_id"]),
                                "remote_path": row.get("remote_path"),
                                "status": _STATUS_FAILED,
                                "reason": _REASON_DB_UPDATE_FAILED,
                                "error": type(batch_exc).__name__,
                            }
                        )
                    files_touched.clear()
                    pending_embedded.clear()

                for chunk_id_ok, fid_ok in pending_embedded:
                    embedded_count += 1
                    per_file_outcomes[fid_ok]["embedded_chunks"] += 1
                for fail in pending_failures:
                    failed_count += 1
                    fid_fail = UUID(fail["file_id"])
                    per_file_outcomes[fid_fail]["failed_chunks"] += 1
                    failure_items.append(fail)

                for fid_local3 in files_touched:
                    try:
                        with conn.transaction():
                            flipped = maybe_mark_file_indexed(
                                conn,
                                file_id=fid_local3,
                                data_source_id=ds_id,
                            )
                        if flipped:
                            per_file_outcomes[fid_local3]["file_index_completed"] = True
                    except psycopg.Error:
                        warnings.append(
                            "files.last_indexed_at bump failed for one or more files"
                        )

                if scan_job_id is not None:
                    _emit_embed_progress(
                        scan_job_id=scan_job_id,
                        heartbeat_worker_id=heartbeat_worker_id,
                        processed_chunks=embedded_count + failed_count,
                        embedded_chunks=embedded_count,
                        failed_chunks=failed_count,
                        skipped_chunks=0,
                        current_path=cur_path or None,
                    )

                if _cancelled() and scan_job_id is not None:
                    scan_jobs_service.mark_job_cancelled(
                        scan_job_id, message=_CANCELLED_MESSAGE
                    )
                    return EmbedPendingChunksCoreResult(
                        payload=_cancelled_payload(
                            ds_id=ds_id,
                            ds_name=ds_name,
                            scan_job_id=scan_job_id,
                            embedding_provider=embedding_provider,
                            embedding_model=embedding_model,
                            expected_dimension=expected_dimension,
                            target_count=target_count,
                            eff_batch=eff_batch,
                            embedded_count=embedded_count,
                            failed_count=failed_count,
                            per_file_outcomes=per_file_outcomes,
                            failure_items=failure_items,
                            warnings=warnings,
                        ),
                        http_status=200,
                        finalized_scan_job=True,
                    )

    except psycopg.Error as outer_exc:
        if scan_job_id is not None:
            scan_jobs_service.fail_scan_job(
                job_id=scan_job_id,
                error_message=f"Database error: {type(outer_exc).__name__}",
            )
        return EmbedPendingChunksCoreResult(
            payload=_error_payload(
                message="Embedding job aborted",
                data_source_id=ds_id,
                scan_job_id=scan_job_id,
                embedding_model=embedding_model,
                error=type(outer_exc).__name__,
            ),
            http_status=500,
            finalized_scan_job=bool(scan_job_id),
        )
    except Exception as exc:  # pragma: no cover - defensive
        if scan_job_id is not None:
            scan_jobs_service.fail_scan_job(
                job_id=scan_job_id,
                error_message=f"Unexpected error: {type(exc).__name__}",
            )
        return EmbedPendingChunksCoreResult(
            payload=_error_payload(
                message="Embedding job aborted",
                data_source_id=ds_id,
                scan_job_id=scan_job_id,
                embedding_model=embedding_model,
                error=type(exc).__name__,
            ),
            http_status=500,
            finalized_scan_job=bool(scan_job_id),
        )

    processed_count = embedded_count + failed_count
    completed_files = sum(
        1 for o in per_file_outcomes.values() if o["file_index_completed"]
    )

    if scan_job_id is not None:
        _emit_embed_progress(
            scan_job_id=scan_job_id,
            heartbeat_worker_id=heartbeat_worker_id,
            processed_chunks=processed_count,
            embedded_chunks=embedded_count,
            failed_chunks=failed_count,
            skipped_chunks=0,
            current_path=None,
        )

    scan_jobs_service.complete_scan_job(
        job_id=scan_job_id,
        total_files=target_count,
        processed_files=processed_count,
        completed_files=embedded_count,
        failed_files=failed_count,
        skipped_files=0,
        deleted_files=0,
    )

    items_out = list(per_file_outcomes.values())
    if failure_items:
        warnings.append(f"{failed_count} chunk(s) failed (see failures[])")

    return EmbedPendingChunksCoreResult(
        payload={
            "status": "ok",
            "data_source_id": str(ds_id),
            "name": ds_name,
            "scan_job_id": str(scan_job_id) if scan_job_id else None,
            "embedding_provider": embedding_provider,
            "embedding_model": embedding_model,
            "expected_dimension": expected_dimension,
            "target_chunks_count": target_count,
            "processed_chunks_count": processed_count,
            "embedded_chunks_count": embedded_count,
            "failed_chunks_count": failed_count,
            "affected_files_count": len(per_file_outcomes),
            "completed_files_count": completed_files,
            "batch_size": eff_batch,
            "dry_run": False,
            "message": SUCCESS_MESSAGE,
            "items": items_out,
            "failures": failure_items,
            "warnings": warnings,
        },
        http_status=200,
        finalized_scan_job=bool(scan_job_id),
    )


def run_embed_pending_chunks(
    settings: Settings,
    ds_id: UUID,
    *,
    limit: int,
    batch_size: int,
    include_extensions: frozenset[str] | None,
    reembed: bool,
    file_id: UUID | None,
    dry_run: bool,
    requested_by: UUID | None = None,
) -> tuple[dict[str, Any], int]:
    """Embed up to ``limit`` chunks for ``ds_id`` and return ``(payload, http_status)``."""
    eff_limit = _clamp(int(limit), _LIMIT_MIN, _LIMIT_MAX)
    eff_batch = _clamp(int(batch_size), _BATCH_MIN, _BATCH_MAX)

    ds_row = datasource_svc.fetch_data_source_row_internal(ds_id=ds_id)
    ds_name = ds_row["name"]

    if file_id is not None:
        owner = fetch_file_for_ownership_check(file_id=file_id)
        if not owner or owner.get("data_source_id") != ds_id:
            raise FileNotInDataSource(
                f"file_id={file_id} does not belong to data_source_id={ds_id}"
            )

    embedding_provider = settings.embedding_provider
    embedding_model = settings.embedding_model
    expected_dimension = int(settings.embedding_dimension)

    rows = fetch_pending_chunks_for_embedding(
        ds_id=ds_id,
        limit=eff_limit,
        include_extensions=include_extensions,
        file_id=file_id,
        reembed=reembed,
    )

    if dry_run:
        return (
            _build_dry_run_payload(
                ds_id=ds_id,
                name=ds_name,
                rows=rows,
                batch_size=eff_batch,
                embedding_model=embedding_model,
                embedding_provider=embedding_provider,
                expected_dimension=expected_dimension,
            ),
            200,
        )

    if not rows:
        return (
            _empty_ok_payload(
                ds_id=ds_id,
                ds_name=ds_name,
                scan_job_id=None,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                expected_dimension=expected_dimension,
                eff_batch=eff_batch,
            ),
            200,
        )

    scan_job_id = scan_jobs_service.create_scan_job(
        ds_id=ds_id,
        job_type=scan_jobs_service.JOB_TYPE_EMBED_PENDING_CHUNKS,
        requested_by=requested_by,
    )

    core = run_embed_pending_chunks_core(
        settings,
        ds_id,
        ds_name=ds_name,
        rows=rows,
        limit=eff_limit,
        batch_size=eff_batch,
        include_extensions=include_extensions,
        reembed=reembed,
        file_id=file_id,
        scan_job_id=scan_job_id,
        requested_by=requested_by,
        cancel_check=None,
        heartbeat_worker_id=None,
    )
    return (core.payload, core.http_status)


# Silence unused-import warnings while keeping ``defaultdict`` available
# for future extensions (e.g. per-extension counters).
_ = defaultdict


__all__ = [
    "EmbedPendingChunksCoreResult",
    "FileNotInDataSource",
    "run_embed_pending_chunks",
    "run_embed_pending_chunks_core",
]
