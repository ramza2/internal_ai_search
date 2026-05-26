"""DB operations for the Step-14 chunk-embedding pass.

Splits the SQL surface in two so the orchestrator
(``chunk_embedding_service``) stays focused on the embedding API loop:

- :func:`fetch_pending_chunks_for_embedding` — joins
  ``document_chunks`` and ``files`` using the Step-14 candidate
  predicate (``COMPLETED``, not ``DELETED``, non-empty ``chunk_text``,
  ``embedding IS NULL`` unless ``reembed=true``) and returns rows
  ordered by ``files.remote_path, document_chunks.chunk_index``.
- :func:`update_chunk_embedding` / :func:`maybe_mark_file_indexed` —
  write paths used inside the per-batch transaction. The orchestrator
  decides when to bump ``files.last_indexed_at`` based on whether
  every chunk for that file has a non-``NULL`` embedding *after* the
  current batch's updates.

Every write is parameter-bound — pgvector values arrive as the
``[v1,v2,...]`` string literal and are cast with ``%s::vector`` to
avoid string-concatenation SQL injection. ``chunk_text`` is *never*
included in responses or returned to the caller from this module; it
flows out only to the embedding HTTP client and is then dropped.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from app.db.database import get_db_connection


# ---- candidate query ------------------------------------------------------

# Step-14 join predicate — see README "Step 14 / 처리 대상" for the
# expanded spec. ``f.analysis_status <> 'DELETED'`` is a belt-and-braces
# guard alongside the explicit ``= 'COMPLETED'`` check so a row that
# transitions to ``DELETED`` after the COMPLETED snapshot still gets
# filtered out.
_FETCH_PENDING_CHUNKS_BASE_SQL = """
    SELECT
        dc.id            AS chunk_id,
        dc.chunk_index   AS chunk_index,
        dc.chunk_text    AS chunk_text,
        dc.file_id       AS file_id,
        f.remote_path    AS remote_path,
        f.filename       AS filename,
        f.extension      AS extension
    FROM document_chunks AS dc
    JOIN files AS f ON f.id = dc.file_id
    WHERE dc.data_source_id = %s
      AND f.data_source_id  = %s
      AND f.is_directory = FALSE
      AND f.analysis_status = 'COMPLETED'::analysis_status
      AND f.analysis_status <> 'DELETED'::analysis_status
      AND dc.chunk_text IS NOT NULL
      AND dc.chunk_text <> ''
"""

_FETCH_FILTER_EMBEDDING_NULL = " AND dc.embedding IS NULL"

_FETCH_FILTER_EXTENSION = (
    " AND lower(nullif(trim(f.extension), '')) = ANY(%s)"
)

_FETCH_FILTER_FILE_ID = " AND f.id = %s"

_FETCH_ORDER_SQL = """
    ORDER BY f.remote_path ASC, dc.chunk_index ASC
"""


def fetch_pending_chunks_for_embedding(
    *,
    ds_id: UUID,
    limit: int,
    include_extensions: frozenset[str] | None,
    file_id: UUID | None,
    reembed: bool,
) -> list[dict[str, Any]]:
    """Return chunk rows to embed in this batch (ordered, limit-bounded).

    The query joins ``document_chunks`` and ``files`` using the
    Step-14 predicate. Both row sets must share the same
    ``data_source_id`` — ``file_id`` (when given) is additionally
    constrained to that data source so a cross-source UUID cannot
    leak chunks here.

    When ``reembed=False`` only ``embedding IS NULL`` rows are
    returned. With ``reembed=True`` every COMPLETED chunk of the
    candidate set is processed regardless of the current embedding
    value, matching the spec's "re-embed even when not NULL" mode.
    """
    params: list[Any] = [ds_id, ds_id]
    sql = _FETCH_PENDING_CHUNKS_BASE_SQL
    if not reembed:
        sql += _FETCH_FILTER_EMBEDDING_NULL
    if include_extensions:
        sql += _FETCH_FILTER_EXTENSION
        params.append(sorted(include_extensions))
    if file_id is not None:
        sql += _FETCH_FILTER_FILE_ID
        params.append(file_id)
    sql += _FETCH_ORDER_SQL
    if limit > 0:
        sql += "    LIMIT %s\n"
        params.append(int(limit))

    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [dict(r) for r in rows]


# ---- file ownership validation -------------------------------------------

_FETCH_FILE_OWNERSHIP_SQL = """
    SELECT
        id,
        data_source_id,
        analysis_status::text AS analysis_status,
        is_directory
    FROM files
    WHERE id = %s
"""


def fetch_file_for_ownership_check(*, file_id: UUID) -> dict[str, Any] | None:
    """Look up a file row by id (returns ``None`` when absent).

    Used by the orchestrator to surface ``FILE_NOT_FOUND_IN_DATA_SOURCE``
    (404) when the request's ``file_id`` either does not exist or
    belongs to a different ``data_source_id`` than the URL one.
    """
    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(_FETCH_FILE_OWNERSHIP_SQL, (file_id,))
            row = cur.fetchone()
    return dict(row) if row else None


# ---- writes ---------------------------------------------------------------


def to_pgvector_literal(vector: list[float]) -> str:
    """Render a Python ``list[float]`` as pgvector's text literal.

    pgvector accepts ``'[v1,v2,...]'`` as a text input that the
    ``::vector`` cast converts into the binary representation. We send
    the literal as a *parameter* (not interpolated) so the value goes
    through psycopg's parameter binding and ``%s::vector`` does the
    cast safely.
    """
    # ``repr``/``str`` of a Python float already produces a SQL-safe
    # representation. Avoid scientific-notation surprises by formatting
    # with ``float.__repr__`` (Python's round-trippable form).
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


_UPDATE_CHUNK_EMBEDDING_SQL = """
    UPDATE document_chunks
    SET embedding = %s::vector
    WHERE id = %s
"""

_UPDATE_CHUNK_EMBEDDING_WITH_MODEL_SQL = """
    UPDATE document_chunks
    SET embedding = %s::vector,
        embedding_model_id = %s
    WHERE id = %s
"""


def update_chunk_embedding(
    conn,
    *,
    chunk_id: UUID,
    vector: list[float],
    embedding_model_id: UUID | None = None,
    has_embedding_model_id_column: bool = False,
) -> int:
    """Write a single chunk's embedding. Caller owns the transaction.

    Returns the affected row count (``1`` on success, ``0`` when the
    chunk disappeared between fetch and update). When the optional
    ``document_chunks.embedding_model_id`` column is present *and* the
    caller has resolved an ``embedding_models`` row, the model id is
    written alongside the vector so downstream search code can attach
    a model badge to results.
    """
    literal = to_pgvector_literal(vector)
    with conn.cursor() as cur:
        if has_embedding_model_id_column and embedding_model_id is not None:
            cur.execute(
                _UPDATE_CHUNK_EMBEDDING_WITH_MODEL_SQL,
                (literal, embedding_model_id, chunk_id),
            )
        else:
            cur.execute(_UPDATE_CHUNK_EMBEDDING_SQL, (literal, chunk_id))
        return int(cur.rowcount or 0)


# ---- per-file "ready for search" flip -------------------------------------

# A file is considered "ready for search" when every one of its
# ``document_chunks`` carries a non-NULL ``embedding`` *and* the file
# itself is still COMPLETED. The flip is implemented as a single SQL
# guard so a concurrent ``DELETED`` transition (or a freshly-failed
# embedding) cannot race the bump.
_MARK_FILE_INDEXED_SQL = """
    UPDATE files AS f
    SET last_indexed_at = NOW(),
        updated_at = NOW()
    WHERE f.id = %s
      AND f.data_source_id = %s
      AND f.analysis_status = 'COMPLETED'::analysis_status
      AND f.analysis_status <> 'DELETED'::analysis_status
      AND EXISTS (
          SELECT 1 FROM document_chunks dc WHERE dc.file_id = f.id
      )
      AND NOT EXISTS (
          SELECT 1 FROM document_chunks dc
          WHERE dc.file_id = f.id
            AND dc.embedding IS NULL
      )
    RETURNING f.id
"""


def maybe_mark_file_indexed(
    conn,
    *,
    file_id: UUID,
    data_source_id: UUID,
) -> bool:
    """Bump ``files.last_indexed_at`` iff every chunk now has an embedding.

    Returns ``True`` when the row was actually updated. The SQL guard
    ensures we *never* mark a file when:

    - any of its chunks still has ``embedding IS NULL`` (e.g. a chunk in
      the current batch failed embedding generation), or
    - the file has zero chunks (defensive — shouldn't happen for
      candidates we just processed, but cheap to guard), or
    - the file transitioned to ``DELETED`` in the meantime.
    """
    with conn.cursor() as cur:
        cur.execute(_MARK_FILE_INDEXED_SQL, (file_id, data_source_id))
        return cur.fetchone() is not None


__all__ = [
    "fetch_file_for_ownership_check",
    "fetch_pending_chunks_for_embedding",
    "maybe_mark_file_indexed",
    "to_pgvector_literal",
    "update_chunk_embedding",
]
