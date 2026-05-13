"""Pydantic models for the search API (Step 15 vector + Step 17 hybrid).

The request model trims / normalizes inputs (extension dots stripped,
``query`` trimmed, ``limit`` / ``min_score`` clamped to safe bounds) so
the service layer never has to second-guess what the client sent. The
response model intentionally omits ``chunk_text`` — only the trimmed
``snippet`` (≤ 300 chars) is exposed to the client.

Step 17 extends both sides with three search modes (vector / keyword /
hybrid). The default stays ``vector`` so existing clients that do not
send ``search_mode`` keep their previous behaviour byte-for-byte.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


QUERY_MIN_LEN = 1
QUERY_MAX_LEN = 2000
LIMIT_MIN = 1
LIMIT_MAX = 100
SCORE_MIN = 0.0
SCORE_MAX = 1.0

WEIGHT_MIN = 0.0
WEIGHT_MAX = 1.0
CANDIDATE_LIMIT_MIN = 1
CANDIDATE_LIMIT_MAX = 200
DEFAULT_VECTOR_CANDIDATE_LIMIT = 50
DEFAULT_KEYWORD_CANDIDATE_LIMIT = 50
DEFAULT_VECTOR_WEIGHT = 0.7
DEFAULT_KEYWORD_WEIGHT = 0.3


class SearchMode(StrEnum):
    """Search strategies supported by ``POST /api/search``.

    - ``VECTOR`` *(default)*: Step-15 behaviour. Embed the query and
      run a pgvector cosine search.
    - ``KEYWORD``: Step-17. ILIKE-based candidate fetch over
      ``files.filename`` / ``files.remote_path`` /
      ``document_chunks.chunk_text``; **no embedding** call.
    - ``HYBRID``: Step-17. Run both paths and merge by ``chunk_id``,
      ranking by ``final_score = (vw*vs + kw*ks) / (vw + kw)``.
    """

    VECTOR = "vector"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


class SearchRequest(BaseModel):
    """Body schema for ``POST /api/search``.

    All optional filters resolve to ``None`` (= unfiltered) when absent
    or empty. ``include_extensions`` is normalized to lowercase tokens
    without a leading dot so the SQL ``= ANY(%s)`` comparison can run
    against ``lower(nullif(trim(files.extension), ''))`` directly.

    Step-17 fields (``search_mode``, weights, candidate limits) only
    matter when the client opts in. The defaults keep the request
    backward compatible with Step-15 clients.
    """

    model_config = ConfigDict(extra="ignore")

    query: Annotated[str, Field(min_length=QUERY_MIN_LEN, max_length=QUERY_MAX_LEN)]
    data_source_id: UUID | None = None
    limit: Annotated[int, Field(ge=LIMIT_MIN, le=LIMIT_MAX)] = 20
    min_score: Annotated[float, Field(ge=SCORE_MIN, le=SCORE_MAX)] = 0.0
    include_extensions: list[str] | None = None
    file_type: str | None = None

    search_mode: SearchMode = SearchMode.VECTOR
    vector_weight: Annotated[
        float, Field(ge=WEIGHT_MIN, le=WEIGHT_MAX)
    ] = DEFAULT_VECTOR_WEIGHT
    keyword_weight: Annotated[
        float, Field(ge=WEIGHT_MIN, le=WEIGHT_MAX)
    ] = DEFAULT_KEYWORD_WEIGHT
    vector_candidate_limit: Annotated[
        int, Field(ge=CANDIDATE_LIMIT_MIN, le=CANDIDATE_LIMIT_MAX)
    ] = DEFAULT_VECTOR_CANDIDATE_LIMIT
    keyword_candidate_limit: Annotated[
        int, Field(ge=CANDIDATE_LIMIT_MIN, le=CANDIDATE_LIMIT_MAX)
    ] = DEFAULT_KEYWORD_CANDIDATE_LIMIT

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

    @field_validator("search_mode", mode="before")
    @classmethod
    def _normalize_search_mode(cls, v):  # type: ignore[no-untyped-def]
        # Accept case-insensitive strings (``"Vector"`` / ``"HYBRID"``)
        # and re-raise unknown values as a ValueError so the route
        # layer can translate them into a 400 envelope.
        if isinstance(v, SearchMode):
            return v
        if isinstance(v, str):
            tok = v.strip().lower()
            for mode in SearchMode:
                if mode.value == tok:
                    return mode
            raise ValueError(
                "search_mode must be one of: vector, keyword, hybrid"
            )
        return v

    @model_validator(mode="after")
    def _validate_hybrid_weights(self):  # type: ignore[no-untyped-def]
        # Sum-of-weights guard: only meaningful for HYBRID. We allow
        # asymmetric weights (e.g. 1.0 / 0.0) but reject 0.0 / 0.0
        # because dividing by the weight sum produces 0 / 0 in the
        # final_score normalization.
        if self.search_mode == SearchMode.HYBRID:
            if (self.vector_weight + self.keyword_weight) <= 0.0:
                raise ValueError(
                    "vector_weight + keyword_weight must be greater than 0 for hybrid"
                )
        return self


class DataSourceScope(BaseModel):
    """Envelope describing the data-source slice the search ran against.

    ``data_source_id`` is ``None`` (and ``data_source_name`` is ``"ALL"``)
    when the request did not narrow the search to a specific source.
    """

    data_source_id: UUID | None = None
    data_source_name: str = "ALL"


class SearchWeights(BaseModel):
    """Echoes the weights actually used for ranking on a hybrid run.

    Always present in the response envelope so the client can see how
    the server interpreted asymmetric / clamped weights. The fields
    fall back to the request defaults for vector / keyword runs.
    """

    vector_weight: float
    keyword_weight: float


class SearchResultItem(BaseModel):
    """One hit. ``chunk_text`` is **never** included — see ``snippet`` instead.

    Step-17 score breakdown:

    - ``score`` — the canonical score the client should sort by. For
      vector mode it equals ``vector_score``; for keyword mode
      ``keyword_score``; for hybrid mode ``final_score``.
    - ``final_score`` — the merged score (always present, equal to
      ``score`` for vector / keyword runs so the response stays
      uniform across modes).
    - ``vector_score`` / ``keyword_score`` — per-source scores; the
      one that did not run is ``None``.
    - ``distance`` — pgvector cosine distance for the underlying
      vector hit. ``None`` for keyword-only matches (no vector
      computed).
    - ``match_reasons`` — keyword match labels (``FILENAME_MATCH``,
      ``PATH_MATCH``, ``CHUNK_TEXT_MATCH``, ``FILENAME_TOKEN_MATCH``,
      ``PATH_TOKEN_MATCH``, ``CHUNK_TOKEN_MATCH``). Empty for
      vector-only matches.
    """

    rank: int
    score: float
    final_score: float
    vector_score: float | None = None
    keyword_score: float | None = None
    distance: float | None = None
    match_reasons: list[str] = []
    search_mode: SearchMode
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
    """Envelope returned by :func:`run_search`. Errors short-circuit before this.

    Step 17:

    - ``search_mode`` carries the mode actually used (after any
      server-side normalization).
    - ``embedding_*`` fields are nullable because keyword-only runs
      do not embed the query and we do not want to fake the dimension
      / model name in that case.
    - ``weights`` echoes the actual blending weights used for hybrid
      runs; for vector / keyword runs the field carries the request
      defaults so the response shape stays uniform.
    """

    status: str = "ok"
    query: str
    search_mode: SearchMode
    embedding_model: str | None = None
    embedding_provider: str | None = None
    expected_dimension: int | None = None
    data_source_scope: DataSourceScope
    total_results: int
    limit: int
    min_score: float
    weights: SearchWeights
    results: list[SearchResultItem]
    message: str


__all__ = [
    "CANDIDATE_LIMIT_MAX",
    "CANDIDATE_LIMIT_MIN",
    "DEFAULT_KEYWORD_CANDIDATE_LIMIT",
    "DEFAULT_KEYWORD_WEIGHT",
    "DEFAULT_VECTOR_CANDIDATE_LIMIT",
    "DEFAULT_VECTOR_WEIGHT",
    "DataSourceScope",
    "LIMIT_MAX",
    "LIMIT_MIN",
    "QUERY_MAX_LEN",
    "QUERY_MIN_LEN",
    "SCORE_MAX",
    "SCORE_MIN",
    "SearchMode",
    "SearchRequest",
    "SearchResponse",
    "SearchResultItem",
    "SearchWeights",
    "WEIGHT_MAX",
    "WEIGHT_MIN",
]
