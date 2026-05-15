"""Pydantic models for ``GET /api/admin/dashboard/summary``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DashboardUsersSummary(BaseModel):
    total: int = 0
    pending: int = 0
    active: int = 0
    inactive: int = 0
    locked: int = 0
    admins: int = 0


class DashboardDataSourcesSummary(BaseModel):
    total: int = 0
    active: int = 0
    inactive: int = 0
    connection_success: int = 0
    connection_failed: int = 0
    never_tested: int = 0


class DashboardFilesSummary(BaseModel):
    total_items: int = 0
    total_files: int = 0
    total_directories: int = 0
    total_size_bytes: int = 0
    total_size_human: str = "0 B"
    pending: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    deleted: int = 0


class DashboardChunksSummary(BaseModel):
    total_chunks: int = 0
    embedded_chunks: int = 0
    pending_embedding_chunks: int = 0


class DashboardActivity24h(BaseModel):
    search_count_24h: int = 0
    rag_count_24h: int = 0
    login_count_24h: int = 0
    failed_action_count_24h: int = 0


class DashboardSummaryBlock(BaseModel):
    users: DashboardUsersSummary
    data_sources: DashboardDataSourcesSummary
    files: DashboardFilesSummary
    chunks: DashboardChunksSummary
    activity: DashboardActivity24h


class RecentScanJobItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    data_source_id: UUID | None = None
    data_source_name: str | None = None
    job_type: str
    status: str
    total_files: int = 0
    processed_files: int = 0
    completed_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    deleted_files: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RecentActionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_name: str | None = None
    action_type: str
    result: str
    search_query: str | None = None
    created_at: datetime | None = None


class DashboardProblemItems(BaseModel):
    failed_files_count: int = 0
    pending_files_count: int = 0
    pending_embedding_chunks_count: int = 0
    inactive_data_sources_count: int = 0
    pending_users_count: int = 0


class RecentPipelineJobItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    data_source_name: str | None = None
    status: str
    progress_percent: float = 0.0
    current_step: str | None = None
    started_at: datetime | None = None


class DashboardPipelinesSummary(BaseModel):
    running: int = 0
    pending: int = 0
    failed_24h: int = 0
    completed_24h: int = 0


class DashboardSummaryResponse(BaseModel):
    status: str = "ok"
    summary: DashboardSummaryBlock
    recent_scan_jobs: list[RecentScanJobItem] = Field(default_factory=list)
    recent_actions: list[RecentActionItem] = Field(default_factory=list)
    problem_items: DashboardProblemItems
    pipelines: DashboardPipelinesSummary = Field(default_factory=DashboardPipelinesSummary)
    recent_pipeline_jobs: list[RecentPipelineJobItem] = Field(default_factory=list)
    message: str = "Dashboard summary retrieved successfully"


__all__ = [
    "DashboardActivity24h",
    "DashboardChunksSummary",
    "DashboardDataSourcesSummary",
    "DashboardFilesSummary",
    "DashboardPipelinesSummary",
    "DashboardProblemItems",
    "DashboardSummaryBlock",
    "DashboardSummaryResponse",
    "DashboardUsersSummary",
    "RecentActionItem",
    "RecentPipelineJobItem",
    "RecentScanJobItem",
]
