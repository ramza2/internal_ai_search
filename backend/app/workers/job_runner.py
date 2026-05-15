"""Dispatch ``WorkerJob`` to handlers.

``WEBDAV_SYNC_TREE`` runs the same core logic as the synchronous HTTP route
when ``job_params.worker_test_mode`` is absent. ``PROCESS_PENDING_TEXT``,
``PROCESS_PENDING_DOCUMENTS``, and ``CHUNK_COMPLETED_TEXT`` run their
respective core functions with the dequeued ``scan_jobs`` row.
``EMBED_PENDING_CHUNKS`` runs :func:`run_embed_pending_chunks_core`.
Other job types remain unimplemented unless flagged for tests.
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.services import scan_jobs_service
from app.services.file_recursive_sync_service import run_webdav_recursive_sync_core
from app.services.chunk_embedding_service import run_embed_pending_chunks_core
from app.services.chunk_text_processor_service import run_chunk_completed_text_core
from app.services.pending_document_processor_service import (
    run_process_pending_documents_core,
)
from app.services.pending_text_processor_service import run_process_pending_text_core
from app.workers.worker_types import WorkerJob, WorkerRunResult

logger = logging.getLogger(__name__)

_TEST_JOB_TYPES = frozenset(
    {
        "MANUAL_SCAN",
        "WEBDAV_SYNC_ROOT",
        "WEBDAV_SYNC_TREE",
        "PROCESS_PENDING_TEXT",
        "PROCESS_PENDING_DOCUMENTS",
        "CHUNK_COMPLETED_TEXT",
        "EMBED_PENDING_CHUNKS",
        "PIPELINE",
    }
)


def _truthy(d: dict[str, Any] | None, key: str) -> bool:
    if not d:
        return False
    v = d.get(key)
    if v is True:
        return True
    if isinstance(v, str) and v.strip().lower() in ("1", "true", "yes"):
        return True
    return False


def _coerce_int(v: Any, default: int, *, lo: int | None = None, hi: int | None = None) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = default
    if lo is not None and n < lo:
        n = lo
    if hi is not None and n > hi:
        n = hi
    return n


def _coerce_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def run_job(job: WorkerJob) -> WorkerRunResult:
    """Execute a claimed job."""
    params = job.job_params if isinstance(job.job_params, dict) else None

    if job.job_type not in _TEST_JOB_TYPES:
        return WorkerRunResult(
            success=False,
            message=f"Unknown job_type: {job.job_type}",
        )

    if _truthy(params, "fail_test"):
        return WorkerRunResult(
            success=False,
            message="fail_test requested (skeleton worker)",
        )

    if _truthy(params, "worker_test_mode"):
        logger.info("worker_test_mode no-op success job_id=%s type=%s", job.id, job.job_type)
        return WorkerRunResult(
            success=True,
            message="No-op test job completed",
            processed_files=0,
            completed_files=0,
            failed_files=0,
            skipped_files=0,
        )

    if job.job_type == scan_jobs_service.JOB_TYPE_PIPELINE:
        if job.data_source_id is None:
            return WorkerRunResult(
                success=False,
                message="PIPELINE job is missing data_source_id",
                finalized_by_handler=False,
            )
        from app.services.pipeline_jobs_service import handle_pipeline_parent_dequeued

        wid = (settings.worker_id or "local-worker-1").strip()[:100]
        return handle_pipeline_parent_dequeued(job, heartbeat_worker_id=wid)

    if job.job_type == "WEBDAV_SYNC_TREE":
        if job.data_source_id is None:
            return WorkerRunResult(
                success=False,
                message="WEBDAV_SYNC_TREE job is missing data_source_id",
            )
        p = params or {}
        start_path = str(p.get("start_path") if p.get("start_path") is not None else "/").strip() or "/"
        max_depth = _coerce_int(p.get("max_depth"), 3, lo=0, hi=20)
        max_items = _coerce_int(p.get("max_items"), 5000, lo=1, hi=50_000)
        include_hidden = bool(p.get("include_hidden", False))
        apply_exclusions = bool(p.get("apply_exclusions", True))
        detect_deleted = bool(p.get("detect_deleted", False))
        wid = (settings.worker_id or "local-worker-1").strip()[:100]

        out = run_webdav_recursive_sync_core(
            settings,
            job.data_source_id,
            scan_job_id=job.id,
            start_path=start_path,
            max_depth=max_depth,
            max_items=max_items,
            include_hidden=include_hidden,
            apply_exclusions=apply_exclusions,
            detect_deleted=detect_deleted,
            requested_by=job.requested_by,
            cancel_check=lambda: scan_jobs_service.is_cancel_requested(job.id),
            heartbeat_worker_id=wid,
        )
        payload = out.payload
        st = str(payload.get("status") or "").lower()
        ok = st in ("ok", "partial")
        msg = str(payload.get("message") or ("Sync finished" if ok else "Sync failed"))
        return WorkerRunResult(
            success=ok,
            message=msg,
            finalized_by_handler=out.finalized_scan_job,
        )

    if job.job_type == scan_jobs_service.JOB_TYPE_PROCESS_PENDING_TEXT:
        if job.data_source_id is None:
            return WorkerRunResult(
                success=False,
                message="PROCESS_PENDING_TEXT job is missing data_source_id",
            )
        p = params or {}
        limit = _coerce_int(p.get("limit"), 100, lo=1, hi=5000)
        max_bytes = _coerce_int(
            p.get("max_file_size_bytes"),
            5_242_880,
            lo=1,
            hi=100 * 1024 * 1024,
        )
        inc_raw = _coerce_str(p.get("include_extensions"))
        wid = (settings.worker_id or "local-worker-1").strip()[:100]

        core = run_process_pending_text_core(
            settings,
            job.data_source_id,
            limit=limit,
            max_file_size_bytes=max_bytes,
            include_extensions=inc_raw,
            scan_job_id=job.id,
            requested_by=job.requested_by,
            cancel_check=lambda: scan_jobs_service.is_cancel_requested(job.id),
            heartbeat_worker_id=wid,
            preflight_ctx=None,
        )
        pl = core.payload
        ok = str(pl.get("status") or "").lower() == "ok"
        msg = str(pl.get("message") or ("Finished" if ok else "Process-pending-text failed"))
        return WorkerRunResult(
            success=ok,
            message=msg,
            finalized_by_handler=core.finalized_scan_job,
        )

    if job.job_type == scan_jobs_service.JOB_TYPE_PROCESS_PENDING_DOCUMENTS:
        if job.data_source_id is None:
            return WorkerRunResult(
                success=False,
                message="PROCESS_PENDING_DOCUMENTS job is missing data_source_id",
            )
        p = params or {}
        limit = _coerce_int(p.get("limit"), 50, lo=1, hi=5000)
        max_bytes = _coerce_int(
            p.get("max_file_size_bytes"),
            52_428_800,
            lo=1,
            hi=100 * 1024 * 1024,
        )
        inc_raw = _coerce_str(p.get("include_extensions"))
        reprocess_skipped = bool(p.get("reprocess_skipped", False))
        wid = (settings.worker_id or "local-worker-1").strip()[:100]

        core = run_process_pending_documents_core(
            settings,
            job.data_source_id,
            limit=limit,
            max_file_size_bytes=max_bytes,
            include_extensions=inc_raw,
            reprocess_skipped=reprocess_skipped,
            scan_job_id=job.id,
            requested_by=job.requested_by,
            cancel_check=lambda: scan_jobs_service.is_cancel_requested(job.id),
            heartbeat_worker_id=wid,
        )
        pl = core.payload
        ok = str(pl.get("status") or "").lower() == "ok"
        msg = str(pl.get("message") or ("Finished" if ok else "Process-pending-documents failed"))
        return WorkerRunResult(
            success=ok,
            message=msg,
            finalized_by_handler=core.finalized_scan_job,
        )

    if job.job_type == scan_jobs_service.JOB_TYPE_CHUNK_COMPLETED_TEXT:
        if job.data_source_id is None:
            return WorkerRunResult(
                success=False,
                message="CHUNK_COMPLETED_TEXT job is missing data_source_id",
            )
        p = params or {}
        limit = _coerce_int(p.get("limit"), 100, lo=1, hi=5000)
        chunk_size = _coerce_int(p.get("chunk_size"), 1200, lo=200, hi=10_000)
        chunk_overlap = _coerce_int(p.get("chunk_overlap"), 200, lo=0, hi=9999)
        min_chunk_size = _coerce_int(p.get("min_chunk_size"), 100, lo=1, hi=10_000)
        reprocess = bool(p.get("reprocess", False))
        inc_raw = _coerce_str(p.get("include_extensions"))
        wid = (settings.worker_id or "local-worker-1").strip()[:100]

        core = run_chunk_completed_text_core(
            job.data_source_id,
            limit=limit,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            min_chunk_size=min_chunk_size,
            reprocess=reprocess,
            include_extensions=inc_raw,
            scan_job_id=job.id,
            requested_by=job.requested_by,
            cancel_check=lambda: scan_jobs_service.is_cancel_requested(job.id),
            heartbeat_worker_id=wid,
        )
        pl = core.payload
        ok = str(pl.get("status") or "").lower() == "ok"
        msg = str(pl.get("message") or ("Finished" if ok else "Chunk-completed-text failed"))
        return WorkerRunResult(
            success=ok,
            message=msg,
            finalized_by_handler=core.finalized_scan_job,
        )

    if job.job_type == scan_jobs_service.JOB_TYPE_EMBED_PENDING_CHUNKS:
        if job.data_source_id is None:
            return WorkerRunResult(
                success=False,
                message="EMBED_PENDING_CHUNKS job is missing data_source_id",
            )
        p = params or {}
        limit = _coerce_int(p.get("limit"), 500, lo=1, hi=10_000)
        batch_size = _coerce_int(p.get("batch_size"), 32, lo=1, hi=128)
        reembed = bool(p.get("reembed", False))
        inc_raw = _coerce_str(p.get("include_extensions"))
        wid = (settings.worker_id or "local-worker-1").strip()[:100]

        core = run_embed_pending_chunks_core(
            settings,
            job.data_source_id,
            ds_name=None,
            rows=None,
            limit=limit,
            batch_size=batch_size,
            include_extensions=inc_raw,
            reembed=reembed,
            file_id=None,
            scan_job_id=job.id,
            requested_by=job.requested_by,
            cancel_check=lambda: scan_jobs_service.is_cancel_requested(job.id),
            heartbeat_worker_id=wid,
        )
        pl = core.payload
        ok = str(pl.get("status") or "").lower() == "ok"
        msg = str(pl.get("message") or ("Finished" if ok else "Embed-pending-chunks failed"))
        return WorkerRunResult(
            success=ok,
            message=msg,
            finalized_by_handler=core.finalized_scan_job,
        )

    return WorkerRunResult(
        success=False,
        message="Worker handler is not implemented for this job type yet",
    )


__all__ = ["run_job"]
