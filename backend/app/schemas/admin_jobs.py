"""Pydantic models for admin scan job list/detail/failures APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AdminJobItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    data_source_id: UUID | None = None
    data_source_name: str | None = None
    job_type: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    progress_percent: float | None = None
    total_files: int = 0
    processed_files: int = 0
    completed_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    deleted_files: int = 0
    current_file_path: str | None = None
    error_message: str | None = None
    requested_by: UUID | None = None
    requested_by_login_id: str | None = None
    requested_by_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Worker-ready fields (migration ``022``); omitted in API when columns absent
    job_params: dict[str, Any] | list[Any] | None = None
    cancel_requested: bool = False
    worker_id: str | None = None
    heartbeat_at: datetime | None = None
    parent_job_id: UUID | None = None
    pipeline_step: str | None = None
    retry_count: int = 0
    max_retries: int = 1
    priority: int = 0


class AdminJobListResponse(BaseModel):
    status: str = "ok"
    total: int = 0
    items: list[AdminJobItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    message: str | None = None


class AdminJobDetailResponse(BaseModel):
    status: str = "ok"
    job: AdminJobItem
    failures_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    message: str = "Job retrieved successfully"


class AdminJobFailureItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    file_id: UUID
    remote_path: str | None = None
    error_code: str
    error_message: str | None = None
    created_at: datetime | None = None


class AdminJobFailuresResponse(BaseModel):
    status: str = "ok"
    job_id: UUID
    total: int = 0
    items: list[AdminJobFailureItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AdminJobErrorResponse(BaseModel):
    status: str = "error"
    message: str
    error: str | None = None


class AdminTestEnqueueRequest(BaseModel):
    """Dev-only body for ``POST /api/admin/jobs/test-enqueue``."""

    data_source_id: UUID | None = None
    job_type: str = "WEBDAV_SYNC_TREE"
    fail_test: bool = False
    priority: int = 0


class AdminTestEnqueueResponse(BaseModel):
    status: str = "ok"
    job_id: UUID
    message: str = "Test job queued successfully"


class AdminSyncTreeJobRequest(BaseModel):
    """Body for ``POST /api/admin/jobs/sync-tree`` (queue PENDING worker job)."""

    data_source_id: UUID
    start_path: str = "/"
    max_depth: int = Field(default=3, ge=0, le=20)
    max_items: int = Field(default=5000, ge=1, le=50_000)
    include_hidden: bool = False
    apply_exclusions: bool = True
    detect_deleted: bool = False
    priority: int = 0

    @field_validator("start_path", mode="before")
    @classmethod
    def normalize_start_path(cls, v: Any) -> str:
        s = str(v or "").strip()
        return s if s else "/"


class AdminSyncTreeJobResponse(BaseModel):
    status: str = "ok"
    job_id: UUID
    job_type: str = "WEBDAV_SYNC_TREE"
    message: str = "Sync-tree job queued successfully"


class AdminJobCancelRequest(BaseModel):
    """Optional body for ``POST /api/admin/jobs/{job_id}/cancel``."""

    reason: str | None = Field(default=None, max_length=500)


class AdminJobCancelResponse(BaseModel):
    status: str = "ok"
    job_id: UUID
    status_after: str
    message: str


__all__ = [
    "AdminJobDetailResponse",
    "AdminJobErrorResponse",
    "AdminJobFailureItem",
    "AdminJobFailuresResponse",
    "AdminJobCancelRequest",
    "AdminJobCancelResponse",
    "AdminJobItem",
    "AdminJobListResponse",
    "AdminSyncTreeJobRequest",
    "AdminSyncTreeJobResponse",
    "AdminTestEnqueueRequest",
    "AdminTestEnqueueResponse",
]
