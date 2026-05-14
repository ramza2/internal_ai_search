"""Admin scan job list/detail/failures plus dev-only test enqueue."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.core.auth_dependencies import CurrentUserContext, require_admin_user
from app.schemas.admin_jobs import (
    AdminSyncTreeJobRequest,
    AdminSyncTreeJobResponse,
    AdminTestEnqueueRequest,
    AdminTestEnqueueResponse,
)
from app.services import admin_jobs_service, scan_jobs_service
from app.services.action_log_service import write_action_log_safe

router = APIRouter(prefix="/api/admin", tags=["admin-jobs"])


@router.get("/jobs", response_model=None)
def admin_list_jobs(
    _: CurrentUserContext = Depends(require_admin_user),
    data_source_id: Annotated[UUID | None, Query(description="Filter by data source")] = None,
    status: Annotated[str | None, Query()] = None,
    job_type: Annotated[str | None, Query()] = None,
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


@router.post("/jobs/sync-tree", response_model=None)
def admin_enqueue_sync_tree_job(
    request: Request,
    body: AdminSyncTreeJobRequest,
    ctx: CurrentUserContext = Depends(require_admin_user),
) -> JSONResponse:
    """Queue a **PENDING** ``WEBDAV_SYNC_TREE`` job for the DB polling worker."""
    job_params = {
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
