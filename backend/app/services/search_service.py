"""Orchestrator for ``POST /api/search`` (Step-15 vector + Step-17 hybrid).

Flow (per ``search_mode``):

- ``VECTOR`` — Step-15 default. Embed the query, run a pgvector cosine
  search against ``document_chunks.embedding``, return top-K.
- ``KEYWORD`` — Step-17. ILIKE-based candidate fetch over
  ``files.filename`` / ``files.remote_path`` /
  ``document_chunks.chunk_text``; **no embedding call**, so the
  endpoint stays usable when Ollama is unreachable.
- ``HYBRID`` — Step-17. Run both candidate fetches with their own
  candidate limits, merge on ``chunk_id``, and rank by a normalized
  ``final_score = (vw*vs + kw*ks) / (vw + kw)``.

Common to every mode:

1. Validate the data-source slice (the request's ``data_source_id``
   must resolve and be active when present; absent ⇒ all active data
   sources).
2. Join ``files`` and ``data_sources`` so each hit carries descriptive
   context (filename, remote_path, data-source name, source_type,
   last_modified, last_indexed_at).
3. Trim each ``chunk_text`` down to a ≤ 300-char snippet — the full
   text never leaves this module.

Out of scope at this milestone: PostgreSQL full-text search
(``tsvector``), BM25 weighting, cross-encoder reranker, RAG / LLM
answer changes, click tracking. Those are deferred follow-ups so the
search pipeline itself stays small and tunable.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.core.config import Settings
from app.db.database import get_db_connection
from app.embedding.ollama_embedding_client import create_embedding
from app.schemas.search import (
    DataSourceScope,
    SearchMode,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SearchWeights,
)
from app.services.chunk_embedding_repository import to_pgvector_literal
from app.utils.file_type import classify_extension
from app.utils.snippet import build_snippet, build_snippet_with_tokens


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


# ---- keyword-search SQL (Step 17) ----------------------------------------

# Use ``!`` as the LIKE escape char to stay portable when
# ``standard_conforming_strings = on`` (same convention as
# ``files_deletion_service``). With this escape:
#
#   - literal ``%`` becomes ``!%``
#   - literal ``_`` becomes ``!_``
#   - literal ``!`` becomes ``!!``
#
# Any other character (including SQL syntax) cannot have a special
# meaning inside a LIKE pattern, so the only escapes we need are the
# wildcards plus the escape char itself.
_LIKE_ESCAPE_CHAR = "!"


def _like_escape(s: str) -> str:
    """Escape ``%`` / ``_`` / escape-char so the literal goes through LIKE intact.

    Mirrors the ``!``-escape convention used in
    ``files_deletion_service`` so the codebase's LIKE patterns share a
    uniform escape semantic regardless of PostgreSQL's
    ``standard_conforming_strings`` setting.
    """
    return (
        s.replace(_LIKE_ESCAPE_CHAR, _LIKE_ESCAPE_CHAR + _LIKE_ESCAPE_CHAR)
        .replace("%", _LIKE_ESCAPE_CHAR + "%")
        .replace("_", _LIKE_ESCAPE_CHAR + "_")
    )


_TOKEN_SPLIT = re.compile(r"\s+")
_MIN_TOKEN_LEN = 2
_MAX_TOKENS = 16


def _normalize_query_tokens(query: str) -> tuple[str, list[str]]:
    """Return ``(phrase, tokens)`` ready for ILIKE comparisons.

    ``phrase`` is the lowercased + trimmed query; ``tokens`` is the
    lowercased whitespace-split list with single-character noise
    dropped (``_MIN_TOKEN_LEN = 2``) and an upper bound applied
    (``_MAX_TOKENS = 16``) so a pathological query cannot blow up the
    ANY() array passed into psycopg.
    """
    phrase = (query or "").strip().lower()
    if not phrase:
        return "", []
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in _TOKEN_SPLIT.split(phrase):
        tok = raw.strip()
        if len(tok) < _MIN_TOKEN_LEN:
            continue
        if tok == phrase:
            # Single-word query — the phrase already covers this case,
            # token-level scoring would double-count.
            continue
        if tok in seen:
            continue
        seen.add(tok)
        tokens.append(tok)
        if len(tokens) >= _MAX_TOKENS:
            break
    return phrase, tokens


def _make_like_patterns(values: list[str]) -> list[str]:
    """Wrap each value as ``%escaped%`` for ``ILIKE`` comparison."""
    return [f"%{_like_escape(v)}%" for v in values]


# SQL is the same set of joins + scope filters as the vector path,
# without any pgvector usage. Candidate fetch is bounded by
# ``keyword_candidate_limit``; final scoring happens in Python.
_KEYWORD_SQL_TEMPLATE = """
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
        ds.source_type::text AS source_type
    FROM document_chunks AS dc
    JOIN files AS f ON f.id = dc.file_id
    JOIN data_sources AS ds ON ds.id = dc.data_source_id
    WHERE dc.chunk_text IS NOT NULL
      AND dc.chunk_text <> ''
      AND f.data_source_id = dc.data_source_id
      AND f.analysis_status = 'COMPLETED'::analysis_status
      AND f.analysis_status <> 'DELETED'::analysis_status
      AND f.is_directory = FALSE
      AND f.last_indexed_at IS NOT NULL
      AND ds.is_active = TRUE
      {extra_filters}
      AND (
          lower(f.filename)        LIKE %s ESCAPE '!'
       OR lower(f.remote_path)     LIKE %s ESCAPE '!'
       OR lower(dc.chunk_text)     LIKE %s ESCAPE '!'
       {token_clauses}
      )
    ORDER BY
        (CASE WHEN lower(f.filename)    LIKE %s ESCAPE '!' THEN 0 ELSE 1 END),
        (CASE WHEN lower(f.remote_path) LIKE %s ESCAPE '!' THEN 0 ELSE 1 END),
        (CASE WHEN lower(dc.chunk_text) LIKE %s ESCAPE '!' THEN 0 ELSE 1 END),
        f.remote_path ASC,
        dc.chunk_index ASC
    LIMIT %s
"""


_TOKEN_CLAUSE_FILENAME = " OR lower(f.filename)    LIKE ANY(%s::text[])"
_TOKEN_CLAUSE_PATH = " OR lower(f.remote_path) LIKE ANY(%s::text[])"
_TOKEN_CLAUSE_CHUNK = " OR lower(dc.chunk_text) LIKE ANY(%s::text[])"


def _execute_keyword_search(
    *,
    phrase: str,
    tokens: list[str],
    ds_id: UUID | None,
    include_extensions: list[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    """ILIKE-based candidate fetch (no embedding call).

    All user-supplied values flow through psycopg parameter binding
    (including the LIKE patterns themselves) so a crafted query cannot
    inject SQL. The ``LIKE ... ESCAPE '!'`` form pairs with
    :func:`_like_escape` so ``%`` / ``_`` inside ``query`` are treated
    as literal characters.
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

    token_clauses_parts: list[str] = []
    token_params: list[Any] = []
    if tokens:
        token_patterns = _make_like_patterns(tokens)
        token_clauses_parts.append(_TOKEN_CLAUSE_FILENAME)
        token_params.append(token_patterns)
        token_clauses_parts.append(_TOKEN_CLAUSE_PATH)
        token_params.append(token_patterns)
        token_clauses_parts.append(_TOKEN_CLAUSE_CHUNK)
        token_params.append(token_patterns)

    sql = _KEYWORD_SQL_TEMPLATE.format(
        extra_filters="\n      ".join(extra_clauses),
        token_clauses="\n       ".join(token_clauses_parts),
    )

    phrase_pattern = f"%{_like_escape(phrase)}%"
    params: list[Any] = [
        *extra_params,
        # WHERE clause: phrase × 3
        phrase_pattern,
        phrase_pattern,
        phrase_pattern,
        # WHERE token arrays (filename, path, chunk_text) when present
        *token_params,
        # ORDER BY priority: phrase × 3
        phrase_pattern,
        phrase_pattern,
        phrase_pattern,
        int(limit),
    ]

    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [dict(r) for r in rows]


# ---- keyword scoring (Python-side) ---------------------------------------

# Per-source contribution. Phrase matches are tracked per-field so a
# single-word query that hits the filename does not double-score by
# also triggering the token-level bonus on the same field.
_KW_PHRASE_FILENAME = 1.0
_KW_PHRASE_PATH = 0.8
_KW_PHRASE_CHUNK = 0.7
_KW_TOKEN_FILENAME = 0.3
_KW_TOKEN_PATH = 0.2
_KW_TOKEN_CHUNK = 0.15

REASON_FILENAME_MATCH = "FILENAME_MATCH"
REASON_PATH_MATCH = "PATH_MATCH"
REASON_CHUNK_MATCH = "CHUNK_TEXT_MATCH"
REASON_FILENAME_TOKEN = "FILENAME_TOKEN_MATCH"
REASON_PATH_TOKEN = "PATH_TOKEN_MATCH"
REASON_CHUNK_TOKEN = "CHUNK_TOKEN_MATCH"


def _compute_keyword_score(
    *,
    row: dict[str, Any],
    phrase: str,
    tokens: list[str],
) -> tuple[float, list[str]]:
    """Score one candidate row + collect ``match_reasons``.

    Score layout (all clamped at 1.0):

    - filename phrase: +1.0    | path phrase: +0.8    | chunk phrase: +0.7
    - filename token:  +0.3    | path token:  +0.2    | chunk token:  +0.15

    Phrase + token in the same field intentionally do not stack —
    that prevents single-word queries from scoring 1.3 when the
    phrase already covered the whole field.
    """
    if not phrase:
        return 0.0, []

    filename = (row.get("filename") or "").lower()
    remote_path = (row.get("remote_path") or "").lower()
    chunk_text = (row.get("chunk_text") or "").lower()

    score = 0.0
    reasons: list[str] = []

    if phrase and phrase in filename:
        score += _KW_PHRASE_FILENAME
        reasons.append(REASON_FILENAME_MATCH)
    elif tokens:
        token_hits = sum(1 for t in tokens if t in filename)
        if token_hits:
            score += _KW_TOKEN_FILENAME * token_hits
            reasons.append(REASON_FILENAME_TOKEN)

    if phrase and phrase in remote_path:
        score += _KW_PHRASE_PATH
        reasons.append(REASON_PATH_MATCH)
    elif tokens:
        token_hits = sum(1 for t in tokens if t in remote_path)
        if token_hits:
            score += _KW_TOKEN_PATH * token_hits
            reasons.append(REASON_PATH_TOKEN)

    if phrase and phrase in chunk_text:
        score += _KW_PHRASE_CHUNK
        reasons.append(REASON_CHUNK_MATCH)
    elif tokens:
        token_hits = sum(1 for t in tokens if t in chunk_text)
        if token_hits:
            score += _KW_TOKEN_CHUNK * token_hits
            reasons.append(REASON_CHUNK_TOKEN)

    if score > 1.0:
        score = 1.0
    if score < 0.0:
        score = 0.0
    return score, reasons


# ---- candidate merge (hybrid) --------------------------------------------


def _row_metadata_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Pick the subset of joined-row fields we need to render a result item.

    Used by the hybrid merge to choose a "preferred" copy of the
    metadata when the same ``chunk_id`` appears in both result sets
    (the vector-side row is preferred because its joined columns
    include the pgvector ``distance`` already).
    """
    return {
        "chunk_id": row.get("chunk_id"),
        "file_id": row.get("file_id"),
        "chunk_index": row.get("chunk_index"),
        "chunk_text": row.get("chunk_text"),
        "start_line": row.get("start_line"),
        "end_line": row.get("end_line"),
        "filename": row.get("filename"),
        "remote_path": row.get("remote_path"),
        "extension": row.get("extension"),
        "last_modified": row.get("last_modified"),
        "last_indexed_at": row.get("last_indexed_at"),
        "data_source_id": row.get("data_source_id"),
        "data_source_name": row.get("data_source_name"),
        "source_type": row.get("source_type"),
    }


def _final_score(
    *, vector_score: float | None, keyword_score: float | None, weights: SearchWeights
) -> float:
    """Normalized weighted blend.

    ``final_score = (vw * vs + kw * ks) / (vw + kw)``

    Missing components contribute ``0`` (the chunk hit only one
    source). Asymmetric weights such as ``vw=1.0, kw=0.0`` collapse
    cleanly because the validator already guarantees the sum is
    positive when ``search_mode == HYBRID``.
    """
    vs = float(vector_score) if vector_score is not None else 0.0
    ks = float(keyword_score) if keyword_score is not None else 0.0
    denom = float(weights.vector_weight) + float(weights.keyword_weight)
    if denom <= 0:
        return 0.0
    return (weights.vector_weight * vs + weights.keyword_weight * ks) / denom


# ---- result-item builder -------------------------------------------------


def _make_result_item(
    *,
    metadata: dict[str, Any],
    rank: int,
    score: float,
    final_score: float,
    vector_score: float | None,
    keyword_score: float | None,
    distance: float | None,
    match_reasons: list[str],
    search_mode: SearchMode,
    snippet_text: str,
) -> SearchResultItem:
    """Build the public-facing :class:`SearchResultItem` from a metadata dict.

    Drops ``chunk_text`` (kept only inside ``metadata`` for the
    in-process RAG caller) and clamps scores to ``[0, 1]`` defensively.
    """

    def _clip(v: float | None) -> float | None:
        if v is None:
            return None
        if v < 0.0:
            return 0.0
        if v > 1.0:
            return 1.0
        return v

    extension = metadata.get("extension")
    file_type = classify_extension(extension)

    return SearchResultItem(
        rank=rank,
        score=round(_clip(score) or 0.0, 6),
        final_score=round(_clip(final_score) or 0.0, 6),
        vector_score=(
            None if vector_score is None else round(_clip(vector_score) or 0.0, 6)
        ),
        keyword_score=(
            None if keyword_score is None else round(_clip(keyword_score) or 0.0, 6)
        ),
        distance=(None if distance is None else round(float(distance), 6)),
        match_reasons=list(match_reasons),
        search_mode=search_mode,
        data_source_id=metadata["data_source_id"],
        data_source_name=str(metadata.get("data_source_name") or ""),
        source_type=str(metadata.get("source_type") or ""),
        file_id=metadata["file_id"],
        filename=metadata.get("filename"),
        remote_path=metadata.get("remote_path"),
        extension=extension,
        file_type=file_type,
        chunk_id=metadata["chunk_id"],
        chunk_index=int(metadata.get("chunk_index") or 0),
        start_line=metadata.get("start_line"),
        end_line=metadata.get("end_line"),
        snippet=snippet_text,
        last_modified=metadata.get("last_modified"),
        last_indexed_at=metadata.get("last_indexed_at"),
    )


# ---- per-mode runners ----------------------------------------------------


def _embed_query(
    settings: Settings, query: str
) -> tuple[str, str, str, int]:
    """Embed ``query`` and return ``(literal, provider, model, expected_dim)``.

    Raised exceptions match the Step-15 contract: connection / parse
    errors become :class:`EmbeddingFailure`, dimension mismatches
    become :class:`EmbeddingFailure(dimension_mismatch=True)`.
    """
    provider = settings.embedding_provider
    model = settings.embedding_model
    expected_dim = int(settings.embedding_dimension)
    emb = create_embedding(
        base_url=settings.ollama_base_url,
        model=model,
        text=query,
        timeout_seconds=settings.embedding_timeout_seconds,
    )
    if not emb.success or emb.vector is None:
        raise EmbeddingFailure(emb.error or "Failed to generate embedding for query")
    if len(emb.vector) != expected_dim:
        raise EmbeddingFailure(
            f"Embedding dimension mismatch: expected {expected_dim}, got {len(emb.vector)}",
            dimension_mismatch=True,
        )
    return to_pgvector_literal(emb.vector), provider, model, expected_dim


def _apply_file_type_post_filter(
    items: list[SearchResultItem], file_type: str | None
) -> list[SearchResultItem]:
    """Python-side ``file_type`` filter shared by every mode.

    The classification SQL would complicate the keyword query; with
    ``limit ≤ 100`` this Python-side filter is effectively free.
    Ranks are recomputed so the response stays self-consistent.
    """
    if not file_type:
        return items
    target = file_type.strip().upper()
    out = [r for r in items if (r.file_type or "").upper() == target]
    for new_rank, r in enumerate(out, start=1):
        r.rank = new_rank
    return out


def _run_vector_mode(
    settings: Settings,
    request: SearchRequest,
    scope: DataSourceScope,
    weights: SearchWeights,
) -> tuple[SearchResponse, dict[str, str]]:
    """Vector-only path. Identical to Step-15 except for the wider response schema."""
    query_vector_literal, provider, model, expected_dim = _embed_query(
        settings, request.query
    )

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

    chunk_text_map: dict[str, str] = {}
    items: list[SearchResultItem] = []
    for i, row in enumerate(rows):
        text = row.get("chunk_text")
        if isinstance(text, str):
            chunk_text_map[str(row["chunk_id"])] = text
        score = float(row.get("score") or 0.0)
        distance = float(row.get("distance") or 0.0)
        items.append(
            _make_result_item(
                metadata=_row_metadata_dict(row),
                rank=i + 1,
                score=score,
                final_score=score,
                vector_score=score,
                keyword_score=None,
                distance=distance,
                match_reasons=[],
                search_mode=SearchMode.VECTOR,
                snippet_text=build_snippet(text, request.query),
            )
        )

    items = _apply_file_type_post_filter(items, request.file_type)

    response = SearchResponse(
        status="ok",
        query=request.query,
        search_mode=SearchMode.VECTOR,
        embedding_model=model,
        embedding_provider=provider,
        expected_dimension=expected_dim,
        data_source_scope=scope,
        total_results=len(items),
        limit=request.limit,
        min_score=request.min_score,
        weights=weights,
        results=items,
        message=SUCCESS_MESSAGE if items else EMPTY_MESSAGE,
    )
    return response, chunk_text_map


def _run_keyword_mode(
    settings: Settings,  # unused but kept for symmetry / future hooks
    request: SearchRequest,
    scope: DataSourceScope,
    weights: SearchWeights,
) -> tuple[SearchResponse, dict[str, str]]:
    """Keyword-only path. **No embedding call** — works while Ollama is down."""
    _ = settings  # silence the unused warning; the signature mirrors the others
    phrase, tokens = _normalize_query_tokens(request.query)
    if not phrase:
        # The schema validator should have caught empty queries; this
        # is a defense-in-depth check.
        return _empty_response(
            request=request,
            scope=scope,
            weights=weights,
            mode=SearchMode.KEYWORD,
        ), {}

    try:
        rows = _execute_keyword_search(
            phrase=phrase,
            tokens=tokens,
            ds_id=request.data_source_id,
            include_extensions=request.include_extensions,
            limit=request.keyword_candidate_limit,
        )
    except psycopg.Error as exc:
        raise SearchDatabaseError(
            f"Keyword search query failed: {type(exc).__name__}"
        ) from exc

    scored: list[tuple[float, list[str], dict[str, Any]]] = []
    chunk_text_map: dict[str, str] = {}
    for row in rows:
        score, reasons = _compute_keyword_score(
            row=row, phrase=phrase, tokens=tokens
        )
        if score < request.min_score:
            continue
        scored.append((score, reasons, row))
        text = row.get("chunk_text")
        if isinstance(text, str):
            chunk_text_map[str(row["chunk_id"])] = text

    # Sort: keyword_score DESC, filename ASC for stability.
    scored.sort(
        key=lambda triple: (
            -triple[0],
            (triple[2].get("filename") or "").lower(),
            (triple[2].get("remote_path") or "").lower(),
            int(triple[2].get("chunk_index") or 0),
        )
    )
    scored = scored[: request.limit]

    items: list[SearchResultItem] = []
    for i, (score, reasons, row) in enumerate(scored):
        text = row.get("chunk_text")
        snippet_text = build_snippet_with_tokens(text, request.query, tokens)
        items.append(
            _make_result_item(
                metadata=_row_metadata_dict(row),
                rank=i + 1,
                score=score,
                final_score=score,
                vector_score=None,
                keyword_score=score,
                distance=None,
                match_reasons=reasons,
                search_mode=SearchMode.KEYWORD,
                snippet_text=snippet_text,
            )
        )

    items = _apply_file_type_post_filter(items, request.file_type)
    # Drop chunk_text entries we didn't end up surfacing.
    kept_ids = {str(it.chunk_id) for it in items}
    chunk_text_map = {k: v for k, v in chunk_text_map.items() if k in kept_ids}

    response = SearchResponse(
        status="ok",
        query=request.query,
        search_mode=SearchMode.KEYWORD,
        # Keyword mode does not embed the query — these stay None to
        # avoid pretending an embedding call ran.
        embedding_model=None,
        embedding_provider=None,
        expected_dimension=None,
        data_source_scope=scope,
        total_results=len(items),
        limit=request.limit,
        min_score=request.min_score,
        weights=weights,
        results=items,
        message=SUCCESS_MESSAGE if items else EMPTY_MESSAGE,
    )
    return response, chunk_text_map


def _run_hybrid_mode(
    settings: Settings,
    request: SearchRequest,
    scope: DataSourceScope,
    weights: SearchWeights,
) -> tuple[SearchResponse, dict[str, str]]:
    """Run vector + keyword candidates and merge on ``chunk_id``."""
    query_vector_literal, provider, model, expected_dim = _embed_query(
        settings, request.query
    )

    # Pull vector candidates without applying min_score — we apply it
    # to the post-merge final_score so a chunk that scored 0.1 on
    # vector but 0.9 on keyword can still surface.
    try:
        vector_rows = _execute_vector_search(
            query_vector_literal=query_vector_literal,
            ds_id=request.data_source_id,
            include_extensions=request.include_extensions,
            min_score=0.0,
            limit=request.vector_candidate_limit,
        )
    except psycopg.Error as exc:
        raise SearchDatabaseError(
            f"Vector search query failed: {type(exc).__name__}"
        ) from exc

    phrase, tokens = _normalize_query_tokens(request.query)
    keyword_rows: list[dict[str, Any]] = []
    if phrase:
        try:
            keyword_rows = _execute_keyword_search(
                phrase=phrase,
                tokens=tokens,
                ds_id=request.data_source_id,
                include_extensions=request.include_extensions,
                limit=request.keyword_candidate_limit,
            )
        except psycopg.Error as exc:
            raise SearchDatabaseError(
                f"Keyword search query failed: {type(exc).__name__}"
            ) from exc

    # Index by chunk_id. Vector-side metadata wins when both sides
    # have a copy (its row already carries the cosine distance).
    merged: dict[str, dict[str, Any]] = {}
    chunk_text_map: dict[str, str] = {}

    for row in vector_rows:
        cid = str(row["chunk_id"])
        merged[cid] = {
            "metadata": _row_metadata_dict(row),
            "vector_score": float(row.get("score") or 0.0),
            "distance": float(row.get("distance") or 0.0),
            "keyword_score": None,
            "match_reasons": [],
        }
        text = row.get("chunk_text")
        if isinstance(text, str):
            chunk_text_map[cid] = text

    for row in keyword_rows:
        cid = str(row["chunk_id"])
        kscore, reasons = _compute_keyword_score(
            row=row, phrase=phrase, tokens=tokens
        )
        if cid in merged:
            merged[cid]["keyword_score"] = kscore
            merged[cid]["match_reasons"] = reasons
        else:
            merged[cid] = {
                "metadata": _row_metadata_dict(row),
                "vector_score": None,
                "distance": None,
                "keyword_score": kscore,
                "match_reasons": reasons,
            }
            text = row.get("chunk_text")
            if isinstance(text, str):
                chunk_text_map[cid] = text

    # Score, threshold, sort.
    scored: list[dict[str, Any]] = []
    for cid, entry in merged.items():
        vs = entry["vector_score"]
        ks = entry["keyword_score"]
        fs = _final_score(vector_score=vs, keyword_score=ks, weights=weights)
        if fs < request.min_score:
            continue
        entry["final_score"] = fs
        entry["chunk_id_str"] = cid
        scored.append(entry)

    scored.sort(
        key=lambda e: (
            -float(e["final_score"]),
            -(float(e["keyword_score"]) if e["keyword_score"] is not None else 0.0),
            -(float(e["vector_score"]) if e["vector_score"] is not None else 0.0),
            (e["metadata"].get("filename") or "").lower(),
        )
    )
    scored = scored[: request.limit]

    items: list[SearchResultItem] = []
    for i, entry in enumerate(scored):
        metadata = entry["metadata"]
        text = metadata.get("chunk_text")
        snippet_text = build_snippet_with_tokens(text, request.query, tokens)
        items.append(
            _make_result_item(
                metadata=metadata,
                rank=i + 1,
                score=float(entry["final_score"]),
                final_score=float(entry["final_score"]),
                vector_score=entry["vector_score"],
                keyword_score=entry["keyword_score"],
                distance=entry["distance"],
                match_reasons=list(entry["match_reasons"]),
                search_mode=SearchMode.HYBRID,
                snippet_text=snippet_text,
            )
        )

    items = _apply_file_type_post_filter(items, request.file_type)
    kept_ids = {str(it.chunk_id) for it in items}
    chunk_text_map = {k: v for k, v in chunk_text_map.items() if k in kept_ids}

    response = SearchResponse(
        status="ok",
        query=request.query,
        search_mode=SearchMode.HYBRID,
        embedding_model=model,
        embedding_provider=provider,
        expected_dimension=expected_dim,
        data_source_scope=scope,
        total_results=len(items),
        limit=request.limit,
        min_score=request.min_score,
        weights=weights,
        results=items,
        message=SUCCESS_MESSAGE if items else EMPTY_MESSAGE,
    )
    return response, chunk_text_map


def _empty_response(
    *,
    request: SearchRequest,
    scope: DataSourceScope,
    weights: SearchWeights,
    mode: SearchMode,
) -> SearchResponse:
    """Build an envelope with zero results in a mode-aware way.

    Used by defensive branches (e.g. tokenization produces nothing
    after the schema-level trim) so the response shape stays uniform.
    """
    return SearchResponse(
        status="ok",
        query=request.query,
        search_mode=mode,
        embedding_model=None,
        embedding_provider=None,
        expected_dimension=None,
        data_source_scope=scope,
        total_results=0,
        limit=request.limit,
        min_score=request.min_score,
        weights=weights,
        results=[],
        message=EMPTY_MESSAGE,
    )


# ---- public dispatcher ----------------------------------------------------


def _run_search_internal(
    settings: Settings, request: SearchRequest
) -> tuple[SearchResponse, dict[str, str]]:
    """Mode dispatcher behind both :func:`run_search` and the RAG helper.

    Returns ``(public_response, chunk_text_map)``. The HTTP route only
    consumes the first element so ``chunk_text`` cannot leak out of
    the application via ``/api/search``.
    """
    scope = _resolve_scope(request.data_source_id)
    weights = SearchWeights(
        vector_weight=request.vector_weight,
        keyword_weight=request.keyword_weight,
    )

    if request.search_mode == SearchMode.KEYWORD:
        return _run_keyword_mode(settings, request, scope, weights)
    if request.search_mode == SearchMode.HYBRID:
        return _run_hybrid_mode(settings, request, scope, weights)
    return _run_vector_mode(settings, request, scope, weights)


def run_search(settings: Settings, request: SearchRequest) -> SearchResponse:
    """Resolve ``request`` against the configured search mode.

    Raises :class:`DataSourceNotFound` (route → 404),
    :class:`EmbeddingFailure` (route → 502), or
    :class:`SearchDatabaseError` (route → 500). The chunk-text map
    produced internally is dropped here — only
    :func:`run_search_with_chunk_texts` exposes it (used by the RAG
    answer service).
    """
    response, _chunk_texts = _run_search_internal(settings, request)
    return response


def run_search_with_chunk_texts(
    settings: Settings, request: SearchRequest
) -> tuple[SearchResponse, dict[str, str]]:
    """In-process variant for the Step-16 RAG path.

    Returns the same public :class:`SearchResponse` plus a
    ``{chunk_id (str) → chunk_text}`` map. **Must not be wired to any
    HTTP route** — the map is the only place chunk_text exits the
    persistence layer.
    """
    return _run_search_internal(settings, request)


__all__ = [
    "DataSourceNotFound",
    "EmbeddingFailure",
    "SearchDatabaseError",
    "run_search",
    "run_search_with_chunk_texts",
]
