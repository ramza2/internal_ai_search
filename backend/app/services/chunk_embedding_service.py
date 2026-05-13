"""Orchestrator for ``POST /api/data-sources/{id}/embed-pending-chunks``.

Pulls ``document_chunks`` rows whose ``embedding IS NULL`` (or every
COMPLETED chunk when ``reembed=true``), generates 1024-D vectors via the
configured Ollama embedding model, and writes them back to
``document_chunks.embedding vector(1024)`` using parameter-bound
``%s::vector`` casts. Once a file's chunks are all embedded the
orchestrator flips ``files.last_indexed_at = NOW()`` — that bump is the
project's "ready for search" signal and is the *only* place in the
codebase that sets ``last_indexed_at``.

Transaction shape (per the spec):

- The embedding HTTP call is performed **outside** any database
  transaction. A single timeout / connection error fails the whole
  batch fast.
- Each Ollama batch of size up to ``batch_size`` translates into one
  short DB transaction containing the per-chunk ``UPDATE`` statements
  and the optional ``last_indexed_at`` bumps. A bad chunk inside a
  batch is rolled back to a per-chunk savepoint so siblings still land.

Out of scope: search APIs, RAG, LLM answer generation, chat, PDF /
DOCX / HWP parsing — none of those run in this milestone.
"""

from __future__ import annotations

from collections import defaultdict, OrderedDict
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


_LIMIT_MIN = 1
_LIMIT_MAX = 5000
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


class FileNotInDataSource(Exception):
    """Surfaced by the route layer as ``404 File not found in data source``."""


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
    """Preserve the fetch order while grouping rows by ``file_id``.

    The candidate query already orders by ``files.remote_path`` then
    ``document_chunks.chunk_index``, so the iteration order of the
    returned mapping matches the order in which file outcomes should be
    reported.
    """
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
    """Embed up to ``limit`` chunks for ``ds_id`` and return ``(payload, http_status)``.

    Raises :class:`datasource_svc.DataSourceNotFound` (mapped to 404 in
    the route layer) and :class:`FileNotInDataSource` (mapped to 404)
    on the easy validation failures; everything else is converted into
    a JSON error payload here so the server process cannot crash on
    Ollama / pgvector / DB hiccups.
    """
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
            {
                "status": "ok",
                "data_source_id": str(ds_id),
                "name": ds_name,
                "scan_job_id": None,
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
            },
            200,
        )

    # Best-effort: register / activate the current model row. May return
    # ``None`` when the ``embedding_models`` table is absent — the
    # orchestrator still writes the embedding vector itself.
    embedding_model_id = embedding_models_service.ensure_embedding_model_registered(
        provider=embedding_provider,
        model=embedding_model,
        dimension=expected_dimension,
    )
    has_model_col = embedding_models_service.column_exists(
        table="document_chunks", column="embedding_model_id"
    )

    scan_job_id = scan_jobs_service.create_scan_job(
        ds_id=ds_id,
        job_type=scan_jobs_service.JOB_TYPE_EMBED_PENDING_CHUNKS,
        requested_by=requested_by,
    )

    target_count = len(rows)
    embedded_count = 0
    failed_count = 0
    warnings: list[str] = []
    per_file_outcomes: "OrderedDict[UUID, dict[str, Any]]" = OrderedDict()

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

    failure_items: list[dict[str, Any]] = []

    try:
        with get_db_connection() as conn:
            for start in range(0, target_count, eff_batch):
                end = min(start + eff_batch, target_count)
                batch = rows[start:end]
                texts = [r["chunk_text"] for r in batch]

                api_result: BatchEmbeddingResult = create_embeddings_batch(
                    base_url=settings.ollama_base_url,
                    model=embedding_model,
                    texts=texts,
                    timeout_seconds=settings.embedding_timeout_seconds,
                )

                # A connection-level batch failure short-circuits the
                # whole run — without an Ollama server we cannot make
                # forward progress and continuing would log misleading
                # per-chunk errors.
                if not api_result.success and api_result.error and all(
                    v is None for v in api_result.vectors
                ):
                    scan_jobs_service.fail_scan_job(
                        job_id=scan_job_id,
                        error_message=api_result.error,
                    )
                    return (
                        _error_payload(
                            message="Failed to generate embeddings",
                            data_source_id=ds_id,
                            scan_job_id=scan_job_id,
                            embedding_model=embedding_model,
                            error=api_result.error,
                        ),
                        502,
                    )

                # Build the per-chunk classification *before* we commit
                # so a failed batch commit can roll back every counter
                # alongside the SQL. ``pending_*`` lists buffer the
                # increments that should fire iff the batch transaction
                # commits successfully.
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
                    # Whole batch rolled back at commit time. Every
                    # candidate becomes a DB-update failure — the
                    # per-chunk savepoint counters were never flushed
                    # because we buffer them above.
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

                # Flush the buffered counters now that the batch's fate
                # is known.
                for chunk_id_ok, fid_ok in pending_embedded:
                    embedded_count += 1
                    per_file_outcomes[fid_ok]["embedded_chunks"] += 1
                for fail in pending_failures:
                    failed_count += 1
                    fid_fail = UUID(fail["file_id"])
                    per_file_outcomes[fid_fail]["failed_chunks"] += 1
                    failure_items.append(fail)

                # After the batch commits, see whether any of the
                # touched files now have *every* chunk embedded — if
                # so, bump ``last_indexed_at`` in a separate short
                # transaction.
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
                        # Bookkeeping failure: leave file_index_completed
                        # as False but don't poison the rest of the run.
                        warnings.append(
                            "files.last_indexed_at bump failed for one or more files"
                        )
    except psycopg.Error as outer_exc:
        scan_jobs_service.fail_scan_job(
            job_id=scan_job_id,
            error_message=f"Database error: {type(outer_exc).__name__}",
        )
        return (
            _error_payload(
                message="Embedding job aborted",
                data_source_id=ds_id,
                scan_job_id=scan_job_id,
                embedding_model=embedding_model,
                error=type(outer_exc).__name__,
            ),
            500,
        )
    except Exception as exc:  # pragma: no cover - defensive
        scan_jobs_service.fail_scan_job(
            job_id=scan_job_id,
            error_message=f"Unexpected error: {type(exc).__name__}",
        )
        return (
            _error_payload(
                message="Embedding job aborted",
                data_source_id=ds_id,
                scan_job_id=scan_job_id,
                embedding_model=embedding_model,
                error=type(exc).__name__,
            ),
            500,
        )

    processed_count = embedded_count + failed_count
    completed_files = sum(
        1 for o in per_file_outcomes.values() if o["file_index_completed"]
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
        warnings.append(
            f"{failed_count} chunk(s) failed (see failures[])"
        )

    return (
        {
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
        200,
    )


# Silence unused-import warnings while keeping ``defaultdict`` available
# for future extensions (e.g. per-extension counters).
_ = defaultdict


__all__ = [
    "FileNotInDataSource",
    "run_embed_pending_chunks",
]
