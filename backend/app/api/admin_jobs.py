"""Admin scan job list/detail/failures plus dev-only test enqueue."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.core.auth_dependencies import CurrentUserContext, require_admin_user
from app.schemas.admin_jobs import (
    AdminChunkCompletedTextJobRequest,
    AdminChunkCompletedTextJobResponse,
    AdminEmbedPendingChunksJobRequest,
    AdminEmbedPendingChunksJobResponse,
    AdminJobCancelResponse,
    AdminJobRetryRequest,
    AdminJobRetryResponse,
    AdminProcessPendingDocumentsJobRequest,
    AdminProcessPendingDocumentsJobResponse,
    AdminProcessPendingTextJobRequest,
    AdminProcessPendingTextJobResponse,
    AdminSyncTreeJobRequest,
    AdminSyncTreeJobResponse,
    AdminTestEnqueueRequest,
    AdminTestEnqueueResponse,
    PROCESS_PENDING_DOCUMENTS_DEFAULT_EXTENSIONS,
    PROCESS_PENDING_TEXT_DEFAULT_EXTENSIONS,
)
from app.schemas.admin_pipeline_jobs import (
    AdminPipelineJobRequest,
    AdminPipelineJobResponse,
)
from app.services import admin_jobs_service, pipeline_jobs_service, scan_jobs_service
from app.services.action_log_service import write_action_log_safe

router = APIRouter(prefix="/api/admin", tags=["admin-jobs"])


@router.get("/jobs", response_model=None)
def admin_list_jobs(
    _: CurrentUserContext = Depends(require_admin_user),
    data_source_id: Annotated[UUID | None, Query(description="Filter by data source")] = None,
    status: Annotated[str | None, Query()] = None,
    job_type: Annotated[str | None, Query()] = None,
    parent_job_id: Annotated[UUID | None, Query(description="Filter by parent scan_jobs.id")] = None,
    keyword: Annotated[str | None, Query()] = None,
    from_date: Annotated[str | None, Query(description="YYYY-MM-DD (created_at)")] = None,
    to_date: Annotated[str | None, Query(description="YYYY-MM-DD (created_at)")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    """List ``scan_jobs`` with filters. Tolerates a missing ``scan_jobs`` table."""
    envelope = admin_jobs_service.list_admin_jobs(
        data_source_id=data_source_id,
        status=status,
        job_type=job_type,
        parent_job_id=parent_job_id,
        keyword=keyword,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(status_code=200, content=envelope.model_dump(mode="json"))


@router.post("/jobs/test-enqueue", response_model=None)
def admin_test_enqueue_job(
    body: AdminTestEnqueueRequest,
    ctx: CurrentUserContext = Depends(require_admin_user),
) -> JSONResponse:
    """Queue a **PENDING** test job for worker skeleton verification (admin only).

    Not for production job creation; a formal ``POST /api/admin/jobs`` is planned.
    Does **not** write ``action_logs`` in this milestone (see README).
    """
    if body.data_source_id is None:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "data_source_id is required",
            },
        )
    jt = (body.job_type or "").strip().upper() or scan_jobs_service.JOB_TYPE_WEBDAV_SYNC_TREE
    if jt == scan_jobs_service.JOB_TYPE_PIPELINE:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "PIPELINE jobs cannot be created via test-enqueue"},
        )
    if jt not in scan_jobs_service.KNOWN_JOB_TYPES:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"Unsupported job_type: {jt}"},
        )
    job_params = {
        "worker_test_mode": True,
        "fail_test": bool(body.fail_test),
        "created_for": "worker_skeleton_test",
    }
    jid = scan_jobs_service.enqueue_scan_job(
        ds_id=body.data_source_id,
        job_type=jt,
        requested_by=ctx.id,
        job_params=job_params,
        priority=int(body.priority),
    )
    if jid is None:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to enqueue test job (DB error or scan_jobs not ready)",
            },
        )
    payload = AdminTestEnqueueResponse(job_id=jid)
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


@router.post("/pipeline-jobs", response_model=None)
def admin_enqueue_pipeline_job(
    request: Request,
    body: AdminPipelineJobRequest,
    ctx: CurrentUserContext = Depends(require_admin_user),
) -> JSONResponse:
    """Queue a server-driven **PIPELINE** parent job (worker advances child jobs sequentially)."""
    assert body.steps is not None
    jid = pipeline_jobs_service.enqueue_pipeline_job(
        data_source_id=body.data_source_id,
        requested_by=ctx.id,
        steps=body.steps,
        params=body.params,
        priority=int(body.priority),
    )
    ok = jid is not None
    write_action_log_safe(
        user_id=ctx.id,
        action_type="JOB_PIPELINE_ENQUEUE",
        result="SUCCESS" if ok else "FAIL",
        request=request,
        data_source_id=body.data_source_id,
        detail={
            "job_id": str(jid) if jid else None,
            "steps": list(body.steps),
            "priority": body.priority,
        },
        error_message=None if ok else "Failed to enqueue pipeline job",
    )
    if not ok:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to enqueue pipeline job (DB error or scan_jobs not ready)",
            },
        )
    payload = AdminPipelineJobResponse(pipeline_job_id=jid)
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


@router.post("/jobs/sync-tree", response_model=None)
def admin_enqueue_sync_tree_job(
    request: Request,
    body: AdminSyncTreeJobRequest,
    ctx: CurrentUserContext = Depends(require_admin_user),
) -> JSONResponse:
    """Queue a **PENDING** ``WEBDAV_SYNC_TREE`` job for the DB polling worker."""
    job_params = {
        "scan_scope": body.scan_scope,
        "start_path": body.start_path,
        "max_depth": body.max_depth,
        "max_items": body.max_items,
        "include_hidden": body.include_hidden,
        "apply_exclusions": body.apply_exclusions,
        "detect_deleted": body.detect_deleted,
        "created_for": "sync_tree_worker",
    }
    jid = scan_jobs_service.enqueue_scan_job(
        ds_id=body.data_source_id,
        job_type=scan_jobs_service.JOB_TYPE_WEBDAV_SYNC_TREE,
        requested_by=ctx.id,
        job_params=job_params,
        priority=int(body.priority),
    )
    ok = jid is not None
    write_action_log_safe(
        user_id=ctx.id,
        action_type="JOB_SYNC_TREE_ENQUEUE",
        result="SUCCESS" if ok else "FAIL",
        request=request,
        data_source_id=body.data_source_id,
        detail={
            "job_id": str(jid) if jid else None,
            "scan_scope": body.scan_scope,
            "start_path": body.start_path,
            "max_depth": body.max_depth,
            "max_items": body.max_items,
            "priority": body.priority,
            "include_hidden": body.include_hidden,
            "apply_exclusions": body.apply_exclusions,
            "detect_deleted": body.detect_deleted,
        },
        error_message=None if ok else "Failed to enqueue sync-tree job",
    )
    if not ok:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to enqueue sync-tree job (DB error or scan_jobs not ready)",
            },
        )
    payload = AdminSyncTreeJobResponse(job_id=jid)
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


@router.post("/jobs/process-pending-text", response_model=None)
def admin_enqueue_process_pending_text_job(
    request: Request,
    body: AdminProcessPendingTextJobRequest,
    ctx: CurrentUserContext = Depends(require_admin_user),
) -> JSONResponse:
    """Queue a **PENDING** ``PROCESS_PENDING_TEXT`` job for the DB polling worker."""
    inc = body.include_extensions or PROCESS_PENDING_TEXT_DEFAULT_EXTENSIONS
    job_params = {
        "limit": int(body.limit),
        "max_file_size_bytes": int(body.max_file_size_bytes),
        "include_extensions": inc,
        "created_for": "process_pending_text_worker",
    }
    jid = scan_jobs_service.enqueue_scan_job(
        ds_id=body.data_source_id,
        job_type=scan_jobs_service.JOB_TYPE_PROCESS_PENDING_TEXT,
        requested_by=ctx.id,
        job_params=job_params,
        priority=int(body.priority),
    )
    ok = jid is not None
    write_action_log_safe(
        user_id=ctx.id,
        action_type="JOB_PROCESS_PENDING_TEXT_ENQUEUE",
        result="SUCCESS" if ok else "FAIL",
        request=request,
        data_source_id=body.data_source_id,
        detail={
            "job_id": str(jid) if jid else None,
            "data_source_id": str(body.data_source_id),
            "limit": body.limit,
            "max_file_size_bytes": body.max_file_size_bytes,
            "include_extensions": inc,
        },
        error_message=None if ok else "Failed to enqueue process-pending-text job",
    )
    if not ok:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to enqueue process-pending-text job (DB error or scan_jobs not ready)",
            },
        )
    payload = AdminProcessPendingTextJobResponse(job_id=jid)
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


@router.post("/jobs/process-pending-documents", response_model=None)
def admin_enqueue_process_pending_documents_job(
    request: Request,
    body: AdminProcessPendingDocumentsJobRequest,
    ctx: CurrentUserContext = Depends(require_admin_user),
) -> JSONResponse:
    """Queue a **PENDING** ``PROCESS_PENDING_DOCUMENTS`` job for the DB polling worker."""
    inc = body.include_extensions or PROCESS_PENDING_DOCUMENTS_DEFAULT_EXTENSIONS
    job_params = {
        "limit": int(body.limit),
        "max_file_size_bytes": int(body.max_file_size_bytes),
        "include_extensions": inc,
        "reprocess_skipped": bool(body.reprocess_skipped),
        "reprocess_hwp_no_extractable_text": bool(body.reprocess_hwp_no_extractable_text),
        "created_for": "process_pending_documents_worker",
    }
    jid = scan_jobs_service.enqueue_scan_job(
        ds_id=body.data_source_id,
        job_type=scan_jobs_service.JOB_TYPE_PROCESS_PENDING_DOCUMENTS,
        requested_by=ctx.id,
        job_params=job_params,
        priority=int(body.priority),
    )
    ok = jid is not None
    write_action_log_safe(
        user_id=ctx.id,
        action_type="JOB_PROCESS_PENDING_DOCUMENTS_ENQUEUE",
        result="SUCCESS" if ok else "FAIL",
        request=request,
        data_source_id=body.data_source_id,
        detail={
            "job_id": str(jid) if jid else None,
            "data_source_id": str(body.data_source_id),
            "limit": body.limit,
            "max_file_size_bytes": body.max_file_size_bytes,
            "include_extensions": inc,
            "reprocess_skipped": body.reprocess_skipped,
            "reprocess_hwp_no_extractable_text": body.reprocess_hwp_no_extractable_text,
        },
        error_message=None if ok else "Failed to enqueue process-pending-documents job",
    )
    if not ok:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to enqueue process-pending-documents job (DB error or scan_jobs not ready)",
            },
        )
    payload = AdminProcessPendingDocumentsJobResponse(job_id=jid)
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


@router.post("/jobs/chunk-completed-text", response_model=None)
def admin_enqueue_chunk_completed_text_job(
    request: Request,
    body: AdminChunkCompletedTextJobRequest,
    ctx: CurrentUserContext = Depends(require_admin_user),
) -> JSONResponse:
    """Queue a **PENDING** ``CHUNK_COMPLETED_TEXT`` job for the DB polling worker."""
    job_params: dict[str, Any] = {
        "limit": int(body.limit),
        "chunk_size": int(body.chunk_size),
        "chunk_overlap": int(body.chunk_overlap),
        "min_chunk_size": int(body.min_chunk_size),
        "reprocess": bool(body.reprocess),
        "created_for": "chunk_completed_text_worker",
    }
    if body.include_extensions is not None:
        job_params["include_extensions"] = body.include_extensions
    jid = scan_jobs_service.enqueue_scan_job(
        ds_id=body.data_source_id,
        job_type=scan_jobs_service.JOB_TYPE_CHUNK_COMPLETED_TEXT,
        requested_by=ctx.id,
        job_params=job_params,
        priority=int(body.priority),
    )
    ok = jid is not None
    detail: dict[str, Any] = {
        "job_id": str(jid) if jid else None,
        "data_source_id": str(body.data_source_id),
        "limit": body.limit,
        "chunk_size": body.chunk_size,
        "chunk_overlap": body.chunk_overlap,
        "min_chunk_size": body.min_chunk_size,
        "reprocess": body.reprocess,
        "include_extensions": body.include_extensions,
    }
    write_action_log_safe(
        user_id=ctx.id,
        action_type="JOB_CHUNK_COMPLETED_TEXT_ENQUEUE",
        result="SUCCESS" if ok else "FAIL",
        request=request,
        data_source_id=body.data_source_id,
        detail=detail,
        error_message=None if ok else "Failed to enqueue chunk-completed-text job",
    )
    if not ok:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to enqueue chunk-completed-text job (DB error or scan_jobs not ready)",
            },
        )
    payload = AdminChunkCompletedTextJobResponse(job_id=jid)
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


@router.post("/jobs/embed-pending-chunks", response_model=None)
def admin_enqueue_embed_pending_chunks_job(
    request: Request,
    body: AdminEmbedPendingChunksJobRequest,
    ctx: CurrentUserContext = Depends(require_admin_user),
) -> JSONResponse:
    """Queue a **PENDING** ``EMBED_PENDING_CHUNKS`` job for the DB polling worker."""
    job_params: dict[str, Any] = {
        "limit": int(body.limit),
        "batch_size": int(body.batch_size),
        "reembed": bool(body.reembed),
        "created_for": "embed_pending_chunks_worker",
    }
    if body.include_extensions is not None:
        job_params["include_extensions"] = body.include_extensions
    jid = scan_jobs_service.enqueue_scan_job(
        ds_id=body.data_source_id,
        job_type=scan_jobs_service.JOB_TYPE_EMBED_PENDING_CHUNKS,
        requested_by=ctx.id,
        job_params=job_params,
        priority=int(body.priority),
    )
    ok = jid is not None
    detail: dict[str, Any] = {
        "job_id": str(jid) if jid else None,
        "data_source_id": str(body.data_source_id),
        "limit": body.limit,
        "batch_size": body.batch_size,
        "include_extensions": body.include_extensions,
        "reembed": body.reembed,
    }
    write_action_log_safe(
        user_id=ctx.id,
        action_type="JOB_EMBED_PENDING_CHUNKS_ENQUEUE",
        result="SUCCESS" if ok else "FAIL",
        request=request,
        data_source_id=body.data_source_id,
        detail=detail,
        error_message=None if ok else "Failed to enqueue embed-pending-chunks job",
    )
    if not ok:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to enqueue embed-pending-chunks job (DB error or scan_jobs not ready)",
            },
        )
    payload = AdminEmbedPendingChunksJobResponse(job_id=jid)
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


@router.post("/jobs/{job_id}/cancel", response_model=None)
async def admin_cancel_job(
    job_id: UUID,
    request: Request,
    ctx: CurrentUserContext = Depends(require_admin_user),
) -> JSONResponse:
    """Cancel a **PENDING** job immediately or request cancel on **RUNNING** (→ ``CANCELLING``)."""
    reason: str | None = None
    try:
        raw = await request.json()
        if isinstance(raw, dict) and raw.get("reason") is not None:
            r = str(raw.get("reason")).strip()
            reason = r[:500] if r else None
    except Exception:
        pass

    res = scan_jobs_service.request_job_cancel(job_id=job_id, reason=reason)
    outcome = str(res.get("result") or "")
    prev = res.get("previous_status")
    after = res.get("status_after")
    msg = str(res.get("message") or "")

    log_ok = outcome in ("ok", "noop_cancelling")
    write_action_log_safe(
        user_id=ctx.id,
        action_type="JOB_CANCEL_REQUEST",
        result="SUCCESS" if log_ok else "FAIL",
        request=request,
        detail={
            "job_id": str(job_id),
            "previous_status": prev,
            "status_after": after,
            "has_reason": bool((reason or "").strip()),
        },
        error_message=None if log_ok else msg,
    )

    if outcome == "not_found":
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Job not found"},
        )
    if outcome == "scan_jobs_missing":
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "scan_jobs table is not available"},
        )
    if outcome == "db_error":
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": msg or "Failed to cancel job"},
        )
    if outcome == "terminal":
        return JSONResponse(
            status_code=409,
            content={"status": "error", "message": msg},
        )

    payload = AdminJobCancelResponse(job_id=job_id, status_after=str(after or ""), message=msg)
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


@router.post("/jobs/{job_id}/retry", response_model=None)
def admin_retry_job(
    job_id: UUID,
    request: Request,
    body: AdminJobRetryRequest,
    ctx: CurrentUserContext = Depends(require_admin_user),
) -> JSONResponse:
    """Queue a new **PENDING** job cloned from a terminal job (manual retry)."""
    res = scan_jobs_service.retry_scan_job(
        job_id=job_id,
        requested_by=ctx.id,
        force=bool(body.force),
        priority=body.priority,
    )
    outcome = str(res.get("result") or "")
    msg = str(res.get("message") or "")
    ds_for_log = res.get("data_source_id")

    def _fail_log(reason_key: str) -> None:
        write_action_log_safe(
            user_id=ctx.id,
            action_type="JOB_RETRY_REQUEST",
            result="FAIL",
            request=request,
            data_source_id=ds_for_log if isinstance(ds_for_log, UUID) else None,
            detail={
                "original_job_id": str(job_id),
                "force": bool(body.force),
                "reason": reason_key,
            },
            error_message=msg or None,
        )

    if outcome == "not_found":
        _fail_log("not_found")
        return JSONResponse(status_code=404, content={"status": "error", "message": "Job not found"})
    if outcome == "scan_jobs_missing":
        _fail_log("scan_jobs_missing")
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "scan_jobs table is not available"},
        )
    if outcome == "not_retryable":
        _fail_log("not_retryable")
        return JSONResponse(
            status_code=409,
            content={"status": "error", "message": msg or "Only FAILED, CANCELLED, or PARTIAL jobs can be retried"},
        )
    if outcome == "max_retries_exceeded":
        _fail_log("max retries exceeded")
        return JSONResponse(
            status_code=409,
            content={"status": "error", "message": msg or "max retries exceeded"},
        )
    if outcome in ("db_error", "enqueue_failed"):
        _fail_log(outcome)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": msg or "Failed to queue retry job"},
        )

    new_id = res.get("new_job_id")
    if not isinstance(new_id, UUID):
        _fail_log("enqueue_failed")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Failed to queue retry job"},
        )

    write_action_log_safe(
        user_id=ctx.id,
        action_type="JOB_RETRY_REQUEST",
        result="SUCCESS",
        request=request,
        data_source_id=ds_for_log if isinstance(ds_for_log, UUID) else None,
        detail={
            "original_job_id": str(job_id),
            "new_job_id": str(new_id),
            "job_type": str(res.get("job_type") or ""),
            "force": bool(body.force),
            "retry_count": int(res.get("retry_count") or 0),
            "max_retries": int(res.get("max_retries") or 1),
        },
        error_message=None,
    )

    payload = AdminJobRetryResponse(
        original_job_id=job_id,
        new_job_id=new_id,
        job_type=str(res.get("job_type") or ""),
        retry_count=int(res.get("retry_count") or 0),
        max_retries=int(res.get("max_retries") or 1),
        message=str(res.get("message") or "Job retry queued successfully"),
    )
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


@router.get("/jobs/{job_id}/children", response_model=None)
def admin_list_job_children(
    job_id: UUID,
    _: CurrentUserContext = Depends(require_admin_user),
) -> JSONResponse:
    """List direct child ``scan_jobs`` rows for a parent job id."""
    res, err = admin_jobs_service.list_admin_job_children(parent_job_id=job_id)
    if err == "not_found":
        return JSONResponse(status_code=404, content={"status": "error", "message": "Job not found"})
    if err == "scan_jobs_missing":
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "scan_jobs table is not available"},
        )
    if err == "db_error" or res is None:
        return JSONResponse(status_code=500, content={"status": "error", "message": "Failed to list child jobs"})
    return JSONResponse(status_code=200, content=res.model_dump(mode="json"))


@router.get("/jobs/{job_id}", response_model=None)
def admin_get_job(
    job_id: UUID,
    _: CurrentUserContext = Depends(require_admin_user),
) -> JSONResponse:
    """Single ``scan_jobs`` row with optional ``scan_failures`` count."""
    detail, err = admin_jobs_service.fetch_admin_job_detail(job_id=job_id)
    if err == "scan_jobs_missing":
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": "scan_jobs table is not available",
            },
        )
    if err == "db_error":
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Failed to retrieve job"},
        )
    if err == "not_found" or detail is None:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Job not found"},
        )
    return JSONResponse(status_code=200, content=detail.model_dump(mode="json"))


@router.get("/jobs/{job_id}/failures", response_model=None)
def admin_list_job_failures(
    job_id: UUID,
    _: CurrentUserContext = Depends(require_admin_user),
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    """Paginated ``scan_failures`` rows for a job."""
    res, err = admin_jobs_service.list_admin_job_failures(job_id=job_id, limit=limit, offset=offset)
    if err == "Job not found":
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Job not found"},
        )
    if err:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": err},
        )
    assert res is not None
    return JSONResponse(status_code=200, content=res.model_dump(mode="json"))


__all__ = ["router"]
