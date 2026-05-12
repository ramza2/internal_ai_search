"""Pydantic models for the Step-16 RAG answer API (``POST /api/answer``).

The request layer mirrors :class:`app.schemas.search.SearchRequest` so a
client that already knows how to call ``POST /api/search`` only needs to
add a handful of LLM-side knobs (``context_limit``, ``answer_min_score``,
``temperature``, ``max_context_chars``, ``dry_run``). All numeric
parameters are clamped server-side so callers cannot blow past resource
limits with a single request.

Schema-side trimming + normalization happens here so the service layer
never sees raw whitespace or duplicate extensions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.search import (
    DataSourceScope,
    LIMIT_MAX as _SEARCH_LIMIT_MAX,
    LIMIT_MIN as _SEARCH_LIMIT_MIN,
    QUERY_MAX_LEN,
    QUERY_MIN_LEN,
    SCORE_MAX,
    SCORE_MIN,
)


SEARCH_LIMIT_MIN = 1
SEARCH_LIMIT_MAX = 50
CONTEXT_LIMIT_MIN = 1
CONTEXT_LIMIT_MAX = 20
TEMPERATURE_MIN = 0.0
TEMPERATURE_MAX = 1.0
MAX_CONTEXT_CHARS_MIN = 1000
MAX_CONTEXT_CHARS_MAX = 30_000
PER_CHUNK_CHARS_MAX = 3000  # internal limit for a single chunk inside the context

# Mirror Step-15 caps in case the search module ever loosens its own
# bounds — the answer endpoint should never exceed the search API's
# ceilings even when the search module raises them.
_SEARCH_LIMIT_MAX_GUARD = min(SEARCH_LIMIT_MAX, _SEARCH_LIMIT_MAX)
_SEARCH_LIMIT_MIN_GUARD = max(SEARCH_LIMIT_MIN, _SEARCH_LIMIT_MIN)


class AnswerRequest(BaseModel):
    """Body schema for ``POST /api/answer``.

    Defaults match the spec: ``search_limit=10``, ``context_limit=5``,
    ``min_score=0.0``, ``answer_min_score=0.2``, ``temperature=0.2``,
    ``max_context_chars=12000``, ``dry_run=False``. Validators trim
    ``query`` and normalize ``include_extensions`` so the RAG service
    can pass them through unchanged.
    """

    model_config = ConfigDict(extra="ignore")

    query: Annotated[str, Field(min_length=QUERY_MIN_LEN, max_length=QUERY_MAX_LEN)]
    data_source_id: UUID | None = None
    search_limit: Annotated[
        int,
        Field(ge=_SEARCH_LIMIT_MIN_GUARD, le=_SEARCH_LIMIT_MAX_GUARD),
    ] = 10
    context_limit: Annotated[
        int, Field(ge=CONTEXT_LIMIT_MIN, le=CONTEXT_LIMIT_MAX)
    ] = 5
    min_score: Annotated[float, Field(ge=SCORE_MIN, le=SCORE_MAX)] = 0.0
    answer_min_score: Annotated[float, Field(ge=SCORE_MIN, le=SCORE_MAX)] = 0.2
    include_extensions: list[str] | None = None
    file_type: str | None = None
    temperature: Annotated[
        float, Field(ge=TEMPERATURE_MIN, le=TEMPERATURE_MAX)
    ] = 0.2
    max_context_chars: Annotated[
        int, Field(ge=MAX_CONTEXT_CHARS_MIN, le=MAX_CONTEXT_CHARS_MAX)
    ] = 12_000
    dry_run: bool = False

    @field_validator("query")
    @classmethod
    def _trim_query(cls, v: str) -> str:
        stripped = (v or "").strip()
        if not stripped:
            # Re-raised as a ValidationError so the route layer can
            # convert it into the spec's ``400 Search query is required``
            # envelope rather than the default 422.
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


class AnswerCitation(BaseModel):
    """One citation row — mirrors Step-15's :class:`SearchResultItem`.

    Carries the same descriptive context (filename / remote_path /
    data source / chunk position / line range / snippet / score) but
    drops the search-specific ``distance`` field and adds nothing
    LLM-derived. Citations are always taken from the actual search
    result, never from anything the model emitted.
    """

    rank: int
    score: float
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


class ContextPreviewItem(BaseModel):
    """One entry in the ``context_preview`` array returned by ``dry_run=true``.

    Carries everything an operator needs to understand what would have
    flowed into the LLM prompt without giving away the full chunk
    body. ``preview_chars`` is the number of characters the LLM would
    have seen for this chunk (after the per-chunk trim); ``snippet``
    is still the same ≤ 300-char string the search API would have
    surfaced.
    """

    context_index: int
    file_id: UUID
    filename: str | None = None
    remote_path: str | None = None
    chunk_id: UUID
    start_line: int | None = None
    end_line: int | None = None
    score: float
    snippet: str
    preview_chars: int


class AnswerSearchEnvelope(BaseModel):
    """Compact search summary inside :class:`AnswerResponse`.

    Exists so the response can carry ``used_context_count`` (which only
    has meaning once context selection has run) alongside the raw
    search counters; the search API itself doesn't need this struct.
    """

    total_results: int
    used_context_count: int
    search_limit: int
    context_limit: int
    answer_min_score: float
    max_context_chars: int
    dropped_for_score: int = 0
    dropped_for_budget: int = 0


class AnswerResponse(BaseModel):
    """Envelope for a successful (or dry-run / no-context) answer call.

    Errors short-circuit before this and use the route layer's bare
    ``{status, message, error?}`` dict instead.
    """

    status: str = "ok"
    query: str
    answer: str | None
    model: str | None
    embedding_model: str
    embedding_provider: str
    data_source_scope: DataSourceScope
    search: AnswerSearchEnvelope
    citations: list[AnswerCitation]
    context_preview: list[ContextPreviewItem] | None = None
    dry_run: bool = False
    message: str
    warnings: list[str] = []
    finish_reason: str | None = None


def public_request_dict(req: AnswerRequest) -> dict[str, Any]:
    """Render the request as JSON-safe primitives for response echoing.

    Excluded fields: ``temperature`` (LLM-side detail) and ``dry_run``
    (already represented in the envelope). The result is intentionally
    small so payload size stays under control.
    """
    return {
        "query": req.query,
        "data_source_id": str(req.data_source_id) if req.data_source_id else None,
        "search_limit": req.search_limit,
        "context_limit": req.context_limit,
        "min_score": req.min_score,
        "answer_min_score": req.answer_min_score,
        "include_extensions": list(req.include_extensions or []),
        "file_type": req.file_type,
        "max_context_chars": req.max_context_chars,
    }


__all__ = [
    "AnswerCitation",
    "AnswerRequest",
    "AnswerResponse",
    "AnswerSearchEnvelope",
    "CONTEXT_LIMIT_MAX",
    "CONTEXT_LIMIT_MIN",
    "ContextPreviewItem",
    "MAX_CONTEXT_CHARS_MAX",
    "MAX_CONTEXT_CHARS_MIN",
    "PER_CHUNK_CHARS_MAX",
    "SEARCH_LIMIT_MAX",
    "SEARCH_LIMIT_MIN",
    "TEMPERATURE_MAX",
    "TEMPERATURE_MIN",
    "public_request_dict",
]
