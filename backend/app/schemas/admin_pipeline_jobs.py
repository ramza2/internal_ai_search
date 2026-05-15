"""Schemas for ``POST /api/admin/pipeline-jobs`` (server-driven PIPELINE parent jobs)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.services.pipeline_jobs_service import normalize_pipeline_steps


class AdminPipelineJobRequest(BaseModel):
    data_source_id: UUID
    priority: int = 0
    steps: list[str] | None = None
    params: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_steps(self) -> AdminPipelineJobRequest:
        steps, err = normalize_pipeline_steps(self.steps)
        if err:
            raise ValueError(err)
        self.steps = steps
        return self


class AdminPipelineJobResponse(BaseModel):
    status: str = "ok"
    pipeline_job_id: UUID
    job_type: str = "PIPELINE"
    message: str = "Pipeline job queued successfully"


class AdminJobChildItem(BaseModel):
    id: UUID
    job_type: str
    pipeline_step: str | None = None
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    progress_percent: float | None = None
    error_message: str | None = None


class AdminJobChildrenSummary(BaseModel):
    total_steps: int = 0
    completed_steps: int = 0
    running_steps: int = 0
    pending_steps: int = 0
    failed_steps: int = 0
    cancelled_steps: int = 0
    partial_steps: int = 0
    progress_percent: float = 0.0
    current_step: str | None = None


class AdminJobChildrenResponse(BaseModel):
    status: str = "ok"
    parent_job_id: UUID
    items: list[AdminJobChildItem] = Field(default_factory=list)
    total: int = 0
    summary: AdminJobChildrenSummary | None = None


__all__ = [
    "AdminJobChildItem",
    "AdminJobChildrenSummary",
    "AdminJobChildrenResponse",
    "AdminPipelineJobRequest",
    "AdminPipelineJobResponse",
]
