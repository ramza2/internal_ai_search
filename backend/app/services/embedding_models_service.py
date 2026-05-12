"""Best-effort registration of the active embedding model.

The application may or may not own an ``embedding_models`` table at this
stage. When the table exists we record the currently-configured provider
/ model / dimension so later analytics and RAG steps can reference it
(``document_chunks.embedding_model_id`` if that column is added).

Failures here **never** block the embedding job — the helper catches
every database error and returns ``None``; the orchestrator still
generates and stores vectors. The same defensive shape is used
elsewhere in the project (see ``scan_jobs_service`` /
``scan_failures_service``).
"""

from __future__ import annotations

from uuid import UUID

from psycopg.rows import dict_row

from app.db.database import get_db_connection


_SELECT_SQL = """
    SELECT id, dimension::int AS dimension
    FROM embedding_models
    WHERE provider = %s AND model_name = %s
    LIMIT 1
"""


_INSERT_SQL = """
    INSERT INTO embedding_models (
        id, provider, model_name, dimension, is_active, created_at, updated_at
    ) VALUES (
        gen_random_uuid(), %s, %s, %s, TRUE, NOW(), NOW()
    )
    RETURNING id, dimension::int AS dimension
"""


_ACTIVATE_SQL = """
    UPDATE embedding_models
    SET is_active = TRUE, updated_at = NOW()
    WHERE id = %s
"""


def ensure_embedding_model_registered(
    *,
    provider: str,
    model: str,
    dimension: int,
) -> UUID | None:
    """Return the row id of the (provider, model) entry, creating it if needed.

    Returns ``None`` when the ``embedding_models`` table or its required
    columns are not present — the caller treats this as "model bookkeeping
    is unavailable on this deployment" and continues normally.
    """
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(_SELECT_SQL, (provider, model))
                row = cur.fetchone()
                if row:
                    cur.execute(_ACTIVATE_SQL, (row["id"],))
                    conn.commit()
                    return row["id"]
                cur.execute(_INSERT_SQL, (provider, model, int(dimension)))
                new_row = cur.fetchone()
            conn.commit()
        return new_row["id"] if new_row else None
    except Exception:
        return None


def column_exists(*, table: str, column: str) -> bool:
    """Return ``True`` when ``table.column`` exists in the current schema.

    Used by the orchestrator to decide whether to write
    ``document_chunks.embedding_model_id``; the column is optional in
    the project's schema today.
    """
    sql = """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND lower(table_name) = lower(%s)
              AND lower(column_name) = lower(%s)
        ) AS present
    """
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(sql, (table, column))
                row = cur.fetchone() or {}
        return bool(row.get("present"))
    except Exception:
        return False
