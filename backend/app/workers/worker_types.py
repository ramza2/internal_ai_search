"""Shared types for the DB-polling worker (skeleton)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class WorkerJob:
    """Row snapshot after ``dequeue_pending_job`` claims a job."""

    id: UUID
    data_source_id: UUID | None
    job_type: str
    job_params: dict[str, Any] | None
    requested_by: UUID | None
    priority: int
    pipeline_step: str | None
    parent_job_id: UUID | None
    max_retries: int
    retry_count: int
    cancel_requested: bool


@dataclass
class WorkerRunResult:
    """Outcome of ``run_job``."""

    success: bool
    message: str
    processed_files: int | None = None
    completed_files: int | None = None
    failed_files: int | None = None
    skipped_files: int | None = None
    finalized_by_handler: bool = False


__all__ = ["WorkerJob", "WorkerRunResult"]
