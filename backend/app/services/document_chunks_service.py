"""DB operations for ``document_chunks`` + COMPLETED-text candidate query.

Step 13 keeps the SQL in one place so the orchestrator can stay focused
on iterating files and slicing text. Every helper here either runs as a
fresh transaction (``fetch_*``, ``has_existing_chunks``) or executes on
a caller-owned connection (``delete_existing_chunks``,
``insert_chunks``) — the latter pair is invoked from inside the
per-file transaction managed by
:mod:`app.services.chunk_text_processor_service`.

This module **never** writes to ``document_chunks.embedding``; that
column is left ``NULL`` for the embedding step that follows.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from app.db.database import get_db_connection
from app.services.chunking_service import Chunk


# Candidate set for chunking:
#
# - file row is COMPLETED and not DELETED (defense in depth),
# - file_contents has a non-empty extracted_text body,
# - optional extension allow-list narrow,
# - optional ``reprocess=false`` ⇒ skip files that already have any chunks.
#
# Ordering matches the Step-12 pattern so re-runs touch the oldest
# COMPLETED rows first.
_FETCH_COMPLETED_BASE_SQL = """
    SELECT
        f.id AS file_id,
        f.remote_path,
        f.filename,
        f.extension,
        f.size_bytes,
        fc.extracted_text,
        fc.text_length
    FROM files AS f
    JOIN file_contents AS fc ON fc.file_id = f.id
    WHERE f.data_source_id = %s
      AND f.is_directory = FALSE
      AND f.analysis_status = 'COMPLETED'::analysis_status
      AND f.analysis_status <> 'DELETED'::analysis_status
      AND fc.extracted_text IS NOT NULL
      AND fc.text_length > 0
"""

_FETCH_EXT_FILTER = (
    " AND lower(nullif(trim(f.extension), '')) = ANY(%s)"
)

# ``NOT EXISTS`` against ``document_chunks`` — only used when
# ``reprocess=false``. With ``reprocess=true`` the orchestrator deletes
# the existing chunks inside the per-file transaction.
_FETCH_SKIP_ALREADY_CHUNKED = """
    AND NOT EXISTS (
        SELECT 1 FROM document_chunks dc
        WHERE dc.file_id = f.id
    )
"""

_FETCH_TAIL = """
    ORDER BY f.updated_at ASC NULLS FIRST, f.remote_path ASC
    LIMIT %s
"""


_HAS_CHUNKS_SQL = """
    SELECT EXISTS (
        SELECT 1 FROM document_chunks WHERE file_id = %s
    ) AS present
"""


_DELETE_FILE_CHUNKS_SQL = (
    "DELETE FROM document_chunks WHERE file_id = %s"
)


_INSERT_CHUNK_SQL = """
INSERT INTO document_chunks (
    id,
    data_source_id,
    file_id,
    chunk_index,
    chunk_text,
    start_line,
    end_line,
    page_number,
    section_title,
    embedding,
    token_count,
    created_at
) VALUES (
    gen_random_uuid(),
    %s, %s, %s, %s,
    %s, %s,
    NULL, NULL,
    NULL,
    %s,
    NOW()
)
"""


def fetch_completed_for_chunking(
    *,
    ds_id: UUID,
    limit: int,
    include_extensions: frozenset[str] | None,
    reprocess: bool,
) -> list[dict[str, Any]]:
    """Return the ordered COMPLETED+file_contents rows ready for chunking.

    Each row carries the joined ``extracted_text`` so the orchestrator
    can avoid a second DB round-trip per file.
    """
    params: list[Any] = [ds_id]
    sql = _FETCH_COMPLETED_BASE_SQL
    if include_extensions:
        sql += _FETCH_EXT_FILTER
        params.append(sorted(include_extensions))
    if not reprocess:
        sql += _FETCH_SKIP_ALREADY_CHUNKED
    sql += _FETCH_TAIL
    params.append(int(limit))

    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def has_existing_chunks(*, file_id: UUID) -> bool:
    """True when at least one ``document_chunks`` row exists for the file.

    Used by ``dry_run`` to classify ``planned_action='SKIP' /
    'ALREADY_CHUNKED'`` without taking a write lock.
    """
    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(_HAS_CHUNKS_SQL, (file_id,))
            row = cur.fetchone() or {}
    return bool(row.get("present"))


def delete_existing_chunks(conn, *, file_id: UUID) -> int:
    """Delete prior chunks for this file. Caller owns the transaction."""
    with conn.cursor() as cur:
        cur.execute(_DELETE_FILE_CHUNKS_SQL, (file_id,))
        return int(cur.rowcount or 0)


def insert_chunks(
    conn,
    *,
    data_source_id: UUID,
    file_id: UUID,
    chunks: list[Chunk],
) -> int:
    """Insert all chunks for one file. Caller owns the transaction.

    ``document_chunks.embedding`` is left ``NULL`` — Step 13's contract.
    Returns the number of rows inserted (``len(chunks)`` on success).
    """
    if not chunks:
        return 0
    payload = [
        (
            data_source_id,
            file_id,
            ch.index,
            ch.text,
            ch.start_line,
            ch.end_line,
            ch.token_count,
        )
        for ch in chunks
    ]
    with conn.cursor() as cur:
        cur.executemany(_INSERT_CHUNK_SQL, payload)
    return len(chunks)
