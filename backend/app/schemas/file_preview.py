"""Pydantic models for Step-18 file / chunk preview APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


CONTEXT_LINES_MIN = 0
CONTEXT_LINES_MAX = 200
CONTEXT_LINES_DEFAULT = 20

MAX_CHARS_MIN = 1000
MAX_CHARS_MAX = 100_000
MAX_CHARS_DEFAULT = 20_000


class FilePreviewOpenInfo(BaseModel):
    """Credential-free WebDAV location hints for a future “open original”."""

    model_config = ConfigDict(extra="ignore")

    data_source_id: UUID
    server_url: str
    webdav_root_path: str | None = None
    remote_path: str
    webdav_url: str


class FilePreviewFileMeta(BaseModel):
    """Public file + data-source slice returned with every preview."""

    model_config = ConfigDict(extra="ignore")

    file_id: UUID
    data_source_id: UUID
    data_source_name: str
    source_type: str
    filename: str | None = None
    remote_path: str | None = None
    extension: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    analysis_status: str
    last_modified: datetime | None = None
    last_indexed_at: datetime | None = None
    open_info: FilePreviewOpenInfo


class PreviewLineItem(BaseModel):
    """One logical line (1-based line number in ``extracted_text``)."""

    model_config = ConfigDict(extra="ignore")

    line: int
    text: str


class FilePreviewBody(BaseModel):
    """Window into ``file_contents.extracted_text``."""

    model_config = ConfigDict(extra="ignore")

    mode: str
    chunk_id: UUID | None = None
    chunk_index: int | None = None
    start_line: int | None = None
    end_line: int | None = None
    requested_start_line: int | None = None
    requested_end_line: int | None = None
    context_lines: int
    is_truncated: bool
    text: str
    lines: list[PreviewLineItem]
    line_count: int
    char_count: int


class FilePreviewSuccessResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str = "ok"
    file: FilePreviewFileMeta
    preview: FilePreviewBody
    highlights: list[dict[str, Any]] = Field(default_factory=list)
    message: str = "File preview retrieved successfully"


class FilePreviewErrorResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str = "error"
    message: str


__all__ = [
    "CONTEXT_LINES_DEFAULT",
    "CONTEXT_LINES_MAX",
    "CONTEXT_LINES_MIN",
    "FilePreviewBody",
    "FilePreviewErrorResponse",
    "FilePreviewFileMeta",
    "FilePreviewOpenInfo",
    "FilePreviewSuccessResponse",
    "MAX_CHARS_DEFAULT",
    "MAX_CHARS_MAX",
    "MAX_CHARS_MIN",
    "PreviewLineItem",
]
