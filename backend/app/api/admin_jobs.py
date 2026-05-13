"""Admin scan job list/detail/failures (read-only, no action_logs)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.core.auth_dependencies import CurrentUserContext, require_admin_user
from app.services import admin_jobs_service

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
