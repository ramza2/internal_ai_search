"""Pydantic models for admin scan job list/detail/failures APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


__all__ = [
    "AdminJobDetailResponse",
    "AdminJobErrorResponse",
    "AdminJobFailureItem",
    "AdminJobFailuresResponse",
    "AdminJobItem",
    "AdminJobListResponse",
]
