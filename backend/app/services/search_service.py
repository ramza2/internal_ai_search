"""Orchestrator for ``POST /api/search`` (Step-15 vector search).

Flow:

1. Validate the data-source slice (the request's ``data_source_id`` must
   resolve and be active when present; absent ⇒ search across every
   active data source).
2. Embed the query string via the Step-3 Ollama embedding client
   (``bge-m3``, 1024-D). Verify the returned dimension matches
   ``EMBEDDING_DIMENSION`` and surface a 502 otherwise — without a
   correctly-sized query vector the ``::vector`` cast would fail at
   the DB layer with a confusing error.
3. Run a cosine-distance pgvector search against ``document_chunks``,
   joining ``files`` and ``data_sources`` so each hit carries
   descriptive context (filename, remote_path, data-source name,
   source_type, last_modified, last_indexed_at).
4. Trim each ``chunk_text`` down to a ≤ 300-char snippet (the full
   text never leaves this module) and return the structured payload.

Out of scope at this milestone: RAG answer generation, LLM chat,
hybrid keyword search, click-tracking, action_logs persistence,
user / RBAC checks. Those land in dedicated follow-up endpoints so the
search pipeline itself can be re-tuned independently of retrieval-aware
features.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.core.config import Settings
from app.db.database import get_db_connection
from app.embedding.ollama_embedding_client import create_embedding
from app.schemas.search import (
    DataSourceScope,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)
from app.services.chunk_embedding_repository import to_pgvector_literal
from app.utils.file_type import classify_extension
from app.utils.snippet import build_snippet


SUCCESS_MESSAGE = "Search completed successfully"
EMPTY_MESSAGE = "No search results found"


class DataSourceNotFound(Exception):
    """Surfaced by the route layer as 404."""


class EmbeddingFailure(Exception):
    """Surfaced by the route layer as 502.

    Carries a short, non-secret reason ("connection refused",
    "dimension mismatch", …) so the response payload stays useful
    without echoing private model / network details.
    """

    def __init__(self, message: str, *, dimension_mismatch: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.dimension_mismatch = dimension_mismatch


class SearchDatabaseError(Exception):
    """Surfaced by the route layer as 500."""


# ---- data-source scope resolution ----------------------------------------


_FETCH_DS_SQL = """
    SELECT id, name, source_type::text AS source_type, is_active
    FROM data_sources
    WHERE id = %s
"""


def _resolve_scope(ds_id: UUID | None) -> DataSourceScope:
    """Return the scope envelope; raise :class:`DataSourceNotFound` when needed.

    A missing or inactive ``data_source_id`` must look identical to the
    client — exposing "exists but inactive" would leak operational
    detail. We treat both as 404s and let the operator inspect the
    server-side log if needed.
    """
    if ds_id is None:
        return DataSourceScope(data_source_id=None, data_source_name="ALL")
    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(_FETCH_DS_SQL, (ds_id,))
            row = cur.fetchone()
    if not row or not row.get("is_active"):
        raise DataSourceNotFound()
    return DataSourceScope(
        data_source_id=ds_id,
        data_source_name=str(row.get("name") or ""),
    )


# ---- vector-search SQL ----------------------------------------------------


# Cosine distance with pgvector: ``a <=> b ∈ [0, 2]``; we report
# ``score = 1 - distance`` so callers see a familiar 0..1-ish bounded
# similarity. ``min_score`` is applied via ``1 - distance >= %s``
# (equivalent to ``distance <= 1 - min_score``) so the index ordering
# stays usable.
#
# Note on bound parameters: psycopg's parameter substitution is
# positional, so the *same* pgvector literal is bound three times — once
# in the SELECT list as ``distance``, once again as the score
# expression (so it stays NUMERICALLY identical), and once in the
# ORDER BY (so the index can serve the sort). Reusing the same literal
# means the SQL planner sees three identical ``%s::vector`` casts
# rather than three different parameters.
_SEARCH_SQL_TEMPLATE = """
    SELECT
        dc.id           AS chunk_id,
        dc.file_id      AS file_id,
        dc.chunk_index  AS chunk_index,
        dc.chunk_text   AS chunk_text,
        dc.start_line   AS start_line,
        dc.end_line     AS end_line,
        f.filename      AS filename,
        f.remote_path   AS remote_path,
        f.extension     AS extension,
        f.last_modified AS last_modified,
        f.last_indexed_at AS last_indexed_at,
        ds.id           AS data_source_id,
        ds.name         AS data_source_name,
        ds.source_type::text AS source_type,
        (dc.embedding <=> %s::vector)        AS distance,
        (1 - (dc.embedding <=> %s::vector))  AS score
    FROM document_chunks AS dc
    JOIN files AS f ON f.id = dc.file_id
    JOIN data_sources AS ds ON ds.id = dc.data_source_id
    WHERE dc.embedding IS NOT NULL
      AND dc.chunk_text IS NOT NULL
      AND dc.chunk_text <> ''
      AND f.data_source_id = dc.data_source_id
      AND f.analysis_status = 'COMPLETED'::analysis_status
      AND f.analysis_status <> 'DELETED'::analysis_status
      AND f.is_directory = FALSE
      AND f.last_indexed_at IS NOT NULL
      AND ds.is_active = TRUE
      {extra_filters}
      AND (1 - (dc.embedding <=> %s::vector)) >= %s
    ORDER BY dc.embedding <=> %s::vector
    LIMIT %s
"""


def _execute_vector_search(
    *,
    query_vector_literal: str,
    ds_id: UUID | None,
    include_extensions: list[str] | None,
    min_score: float,
    limit: int,
) -> list[dict[str, Any]]:
    """Run the cosine-distance query and return the joined rows.

    The pgvector literal is passed as a *parameter* (psycopg binds it
    with ``%s::vector``); never concatenated into the SQL string.
    Filter clauses are likewise built from parameter slots, so a
    crafted ``include_extensions`` value can't poison the query.
    """
    extra_clauses: list[str] = []
    extra_params: list[Any] = []
    if ds_id is not None:
        extra_clauses.append("AND f.data_source_id = %s")
        extra_params.append(ds_id)
    if include_extensions:
        extra_clauses.append(
            "AND lower(nullif(trim(f.extension), '')) = ANY(%s)"
        )
        extra_params.append(list(include_extensions))

    sql = _SEARCH_SQL_TEMPLATE.format(
        extra_filters="\n      ".join(extra_clauses)
    )

    params: list[Any] = [
        query_vector_literal,  # distance in SELECT
        query_vector_literal,  # score in SELECT
        *extra_params,
        query_vector_literal,  # score guard in WHERE
        float(min_score),
        query_vector_literal,  # ORDER BY
        int(limit),
    ]

    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [dict(r) for r in rows]


# ---- public entry point ---------------------------------------------------


def _make_result_item(
    *,
    row: dict[str, Any],
    rank: int,
    query: str,
) -> SearchResultItem:
    """Translate one joined DB row into a public :class:`SearchResultItem`.

    Strips ``chunk_text`` and replaces it with a ≤ 300-char snippet,
    populates the optional ``file_type`` label using the canonical
    extension classifier (so search results report the same
    ``DOCUMENT/SOURCE_CODE/...`` buckets as the file-statistics API),
    and clamps numeric fields with a defensive ``float()`` /
    ``int()`` cast in case psycopg surfaces a ``Decimal`` for the
    distance expression.
    """
    distance_raw = row.get("distance")
    score_raw = row.get("score")
    distance = float(distance_raw) if distance_raw is not None else 0.0
    score = float(score_raw) if score_raw is not None else 0.0

    extension = row.get("extension")
    file_type = classify_extension(extension)

    snippet = build_snippet(row.get("chunk_text"), query)

    return SearchResultItem(
        rank=rank,
        score=round(score, 6),
        distance=round(distance, 6),
        data_source_id=row["data_source_id"],
        data_source_name=str(row.get("data_source_name") or ""),
        source_type=str(row.get("source_type") or ""),
        file_id=row["file_id"],
        filename=row.get("filename"),
        remote_path=row.get("remote_path"),
        extension=extension,
        file_type=file_type,
        chunk_id=row["chunk_id"],
        chunk_index=int(row.get("chunk_index") or 0),
        start_line=row.get("start_line"),
        end_line=row.get("end_line"),
        snippet=snippet,
        last_modified=row.get("last_modified"),
        last_indexed_at=row.get("last_indexed_at"),
    )


def _run_search_internal(
    settings: Settings, request: SearchRequest
) -> tuple[SearchResponse, dict[str, str]]:
    """Shared implementation behind :func:`run_search` and the RAG helper.

    Returns ``(public_response, chunk_text_map)``. The map's keys are
    ``str(chunk_id)`` so callers can look up the raw text without
    re-running the SQL or threading it through the public response
    schema. The HTTP route only ever consumes the first element so
    ``chunk_text`` cannot leak out of the application.
    """
    scope = _resolve_scope(request.data_source_id)

    provider = settings.embedding_provider
    model = settings.embedding_model
    expected_dim = int(settings.embedding_dimension)

    emb = create_embedding(
        base_url=settings.ollama_base_url,
        model=model,
        text=request.query,
        timeout_seconds=settings.embedding_timeout_seconds,
    )
    if not emb.success or emb.vector is None:
        raise EmbeddingFailure(
            emb.error or "Failed to generate embedding for query"
        )
    if len(emb.vector) != expected_dim:
        raise EmbeddingFailure(
            f"Embedding dimension mismatch: expected {expected_dim}, got {len(emb.vector)}",
            dimension_mismatch=True,
        )

    query_vector_literal = to_pgvector_literal(emb.vector)

    try:
        rows = _execute_vector_search(
            query_vector_literal=query_vector_literal,
            ds_id=request.data_source_id,
            include_extensions=request.include_extensions,
            min_score=request.min_score,
            limit=request.limit,
        )
    except psycopg.Error as exc:
        raise SearchDatabaseError(
            f"Vector search query failed: {type(exc).__name__}"
        ) from exc

    # Preserve a parallel ``chunk_id (str) → chunk_text`` map for the
    # in-process RAG caller before snippet generation drops the body.
    chunk_text_map: dict[str, str] = {}
    for row in rows:
        cid = row.get("chunk_id")
        text = row.get("chunk_text")
        if cid is not None and isinstance(text, str):
            chunk_text_map[str(cid)] = text

    results = [
        _make_result_item(row=row, rank=i + 1, query=request.query)
        for i, row in enumerate(rows)
    ]

    if request.file_type:
        # Spec allows ``include_extensions`` only at the DB layer and
        # treats ``file_type`` as optional. We honour ``file_type`` here
        # via a Python-side post-filter so the SQL stays simple — the
        # classifier already enumerates the canonical buckets and this
        # endpoint typically receives ``limit ≤ 100`` rows, making
        # post-filtering cheap.
        target = request.file_type.strip().upper()
        results = [r for r in results if (r.file_type or "").upper() == target]
        for new_rank, r in enumerate(results, start=1):
            r.rank = new_rank

    message = SUCCESS_MESSAGE if results else EMPTY_MESSAGE

    response = SearchResponse(
        status="ok",
        query=request.query,
        embedding_model=model,
        embedding_provider=provider,
        expected_dimension=expected_dim,
        data_source_scope=scope,
        total_results=len(results),
        limit=request.limit,
        min_score=request.min_score,
        results=results,
        message=message,
    )
    return response, chunk_text_map


def run_search(settings: Settings, request: SearchRequest) -> SearchResponse:
    """Resolve ``request`` against the embedding model + pgvector store.

    Raises :class:`DataSourceNotFound` (route → 404),
    :class:`EmbeddingFailure` (route → 502), or
    :class:`SearchDatabaseError` (route → 500) for the failure shapes
    callers need to differentiate. Everything else propagates as a
    plain exception to the route's generic 500 handler.

    NOTE: per the Step-15 spec, hybrid keyword search (``filename`` /
    ``remote_path`` ``ILIKE``) is deliberately deferred to a later
    milestone. The vector path is implemented in isolation here so its
    behaviour can be tuned (re-rankers, score thresholds, …) without
    disturbing keyword-side ranking decisions. TODO(step-17): add an
    optional hybrid keyword score that boosts hits whose
    ``filename``/``remote_path`` literally contain the query.
    """
    response, _chunk_texts = _run_search_internal(settings, request)
    return response


def run_search_with_chunk_texts(
    settings: Settings, request: SearchRequest
) -> tuple[SearchResponse, dict[str, str]]:
    """In-process variant of :func:`run_search` for the Step-16 RAG path.

    Returns the same public :class:`SearchResponse` plus a
    ``{chunk_id (str) → chunk_text}`` map. **Must not be wired to any
    HTTP route** — the map is the only place chunk_text exits the
    persistence layer, and the project's contract is that the public
    search response never carries the full text. The Step-16 RAG
    answer service consumes this directly to build the LLM context.
    """
    return _run_search_internal(settings, request)


__all__ = [
    "DataSourceNotFound",
    "EmbeddingFailure",
    "SearchDatabaseError",
    "run_search",
    "run_search_with_chunk_texts",
]
