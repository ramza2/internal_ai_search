"""Pydantic models for admin scan job list/detail/failures APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


PROCESS_PENDING_TEXT_DEFAULT_EXTENSIONS = (
    "txt,md,py,java,sql,json,yml,yaml,log,csv"
)


class AdminProcessPendingTextJobRequest(BaseModel):
    """Body for ``POST /api/admin/jobs/process-pending-text`` (worker queue)."""

    data_source_id: UUID
    limit: int = Field(default=100, ge=1, le=5000)
    max_file_size_bytes: int = Field(default=5_242_880, ge=1, le=100 * 1024 * 1024)
    include_extensions: str | None = Field(default=None, max_length=2000)
    priority: int = 0

    @field_validator("include_extensions", mode="before")
    @classmethod
    def normalize_include_extensions(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None


class AdminProcessPendingTextJobResponse(BaseModel):
    status: str = "ok"
    job_id: UUID
    job_type: str = "PROCESS_PENDING_TEXT"
    message: str = "Process-pending-text job queued successfully"


PROCESS_PENDING_DOCUMENTS_DEFAULT_EXTENSIONS = "pdf,docx,xlsx,pptx,hwpx"


class AdminProcessPendingDocumentsJobRequest(BaseModel):
    """Body for ``POST /api/admin/jobs/process-pending-documents`` (worker queue)."""

    data_source_id: UUID
    limit: int = Field(default=50, ge=1, le=5000)
    max_file_size_bytes: int = Field(default=52_428_800, ge=1, le=100 * 1024 * 1024)
    include_extensions: str | None = Field(default=None, max_length=2000)
    reprocess_skipped: bool = False
    priority: int = 0

    @field_validator("include_extensions", mode="before")
    @classmethod
    def normalize_include_extensions_doc(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None


class AdminProcessPendingDocumentsJobResponse(BaseModel):
    status: str = "ok"
    job_id: UUID
    job_type: str = "PROCESS_PENDING_DOCUMENTS"
    message: str = "Process-pending-documents job queued successfully"


class AdminChunkCompletedTextJobRequest(BaseModel):
    """Body for ``POST /api/admin/jobs/chunk-completed-text`` (worker queue)."""

    data_source_id: UUID
    limit: int = Field(default=100, ge=1, le=5000)
    chunk_size: int = Field(default=1200, ge=200, le=10_000)
    chunk_overlap: int = Field(default=200, ge=0, le=9999)
    min_chunk_size: int = Field(default=100, ge=1, le=10_000)
    reprocess: bool = False
    include_extensions: str | None = Field(default=None, max_length=2000)
    priority: int = 0

    @field_validator("include_extensions", mode="before")
    @classmethod
    def normalize_include_extensions_chunk(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    @model_validator(mode="after")
    def overlap_smaller_than_chunk(self) -> AdminChunkCompletedTextJobRequest:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self


class AdminChunkCompletedTextJobResponse(BaseModel):
    status: str = "ok"
    job_id: UUID
    job_type: str = "CHUNK_COMPLETED_TEXT"
    message: str = "Chunk-completed-text job queued successfully"


class AdminEmbedPendingChunksJobRequest(BaseModel):
    """Body for ``POST /api/admin/jobs/embed-pending-chunks`` (worker queue)."""

    data_source_id: UUID
    limit: int = Field(default=500, ge=1, le=10_000)
    batch_size: int = Field(default=32, ge=1, le=128)
    include_extensions: str | None = Field(default=None, max_length=2000)
    reembed: bool = False
    priority: int = 0

    @field_validator("include_extensions", mode="before")
    @classmethod
    def normalize_include_extensions_embed(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None


class AdminEmbedPendingChunksJobResponse(BaseModel):
    status: str = "ok"
    job_id: UUID
    job_type: str = "EMBED_PENDING_CHUNKS"
    message: str = "Embed-pending-chunks job queued successfully"


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
    "AdminProcessPendingTextJobRequest",
    "AdminProcessPendingTextJobResponse",
    "AdminProcessPendingDocumentsJobRequest",
    "AdminProcessPendingDocumentsJobResponse",
    "PROCESS_PENDING_DOCUMENTS_DEFAULT_EXTENSIONS",
    "AdminChunkCompletedTextJobRequest",
    "AdminChunkCompletedTextJobResponse",
    "AdminEmbedPendingChunksJobRequest",
    "AdminEmbedPendingChunksJobResponse",
    "AdminSyncTreeJobRequest",
    "AdminSyncTreeJobResponse",
    "AdminTestEnqueueRequest",
    "AdminTestEnqueueResponse",
    "PROCESS_PENDING_TEXT_DEFAULT_EXTENSIONS",
]
