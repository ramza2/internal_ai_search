"""Pydantic models for the Step-15 search API.

The request model trims / normalizes inputs (extension dots stripped,
``query`` trimmed, ``limit`` / ``min_score`` clamped to safe bounds) so
the service layer never has to second-guess what the client sent. The
response model intentionally omits ``chunk_text`` — only the trimmed
``snippet`` (≤ 300 chars) is exposed to the client.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


QUERY_MIN_LEN = 1
QUERY_MAX_LEN = 2000
LIMIT_MIN = 1
LIMIT_MAX = 100
SCORE_MIN = 0.0
SCORE_MAX = 1.0


class SearchRequest(BaseModel):
    """Body schema for ``POST /api/search``.

    All optional filters resolve to ``None`` (= unfiltered) when absent
    or empty. ``include_extensions`` is normalized to lowercase tokens
    without a leading dot so the SQL ``= ANY(%s)`` comparison can run
    against ``lower(nullif(trim(files.extension), ''))`` directly.
    """

    model_config = ConfigDict(extra="ignore")

    query: Annotated[str, Field(min_length=QUERY_MIN_LEN, max_length=QUERY_MAX_LEN)]
    data_source_id: UUID | None = None
    limit: Annotated[int, Field(ge=LIMIT_MIN, le=LIMIT_MAX)] = 20
    min_score: Annotated[float, Field(ge=SCORE_MIN, le=SCORE_MAX)] = 0.0
    include_extensions: list[str] | None = None
    file_type: str | None = None

    @field_validator("query")
    @classmethod
    def _trim_query(cls, v: str) -> str:
        stripped = (v or "").strip()
        if not stripped:
            # Re-raise as ValueError so FastAPI surfaces a 422 with a
            # body the route layer translates into a 400 "Search query
            # is required" payload to match the spec.
            raise ValueError("Search query is required")
        return stripped

    @field_validator("include_extensions")
    @classmethod
    def _normalize_extensions(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in v:
            if not isinstance(raw, str):
                continue
            tok = raw.strip().lower()
            if tok.startswith("."):
                tok = tok[1:].strip()
            if not tok or tok in seen:
                continue
            seen.add(tok)
            cleaned.append(tok)
        return cleaned or None

    @field_validator("file_type")
    @classmethod
    def _normalize_file_type(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip().upper()
        return s or None


class DataSourceScope(BaseModel):
    """Envelope describing the data-source slice the search ran against.

    ``data_source_id`` is ``None`` (and ``data_source_name`` is ``"ALL"``)
    when the request did not narrow the search to a specific source.
    """

    data_source_id: UUID | None = None
    data_source_name: str = "ALL"


class SearchResultItem(BaseModel):
    """One hit. ``chunk_text`` is **never** included — see ``snippet`` instead."""

    rank: int
    score: float
    distance: float
    data_source_id: UUID
    data_source_name: str
    source_type: str
    file_id: UUID
    filename: str | None = None
    remote_path: str | None = None
    extension: str | None = None
    file_type: str | None = None
    chunk_id: UUID
    chunk_index: int
    start_line: int | None = None
    end_line: int | None = None
    snippet: str
    last_modified: datetime | None = None
    last_indexed_at: datetime | None = None


class SearchResponse(BaseModel):
    """Envelope returned by :func:`run_search`. Errors short-circuit before this."""

    status: str = "ok"
    query: str
    embedding_model: str
    embedding_provider: str
    expected_dimension: int
    data_source_scope: DataSourceScope
    total_results: int
    limit: int
    min_score: float
    results: list[SearchResultItem]
    message: str


__all__ = [
    "DataSourceScope",
    "QUERY_MAX_LEN",
    "QUERY_MIN_LEN",
    "SearchRequest",
    "SearchResponse",
    "SearchResultItem",
]
