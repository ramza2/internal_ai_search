from typing import Any

from psycopg.rows import dict_row

from app.db.database import get_db_connection


def check_db_health() -> dict[str, Any]:
    try:
        with get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        current_database() AS database,
                        current_user AS user_name,
                        version() AS postgres_version
                    """
                )
                db_info = cur.fetchone()

                cur.execute(
                    """
                    SELECT
                        EXISTS (
                            SELECT 1
                            FROM pg_extension
                            WHERE extname = 'vector'
                        ) AS pgvector_enabled,
                        (
                            SELECT extversion
                            FROM pg_extension
                            WHERE extname = 'vector'
                        ) AS pgvector_version
                    """
                )
                vector_info = cur.fetchone()

                return {
                    "ok": True,
                    "database": db_info["database"],
                    "user": db_info["user_name"],
                    "postgres_version": db_info["postgres_version"],
                    "pgvector_enabled": vector_info["pgvector_enabled"],
                    "pgvector_version": vector_info["pgvector_version"],
                    "error": None,
                }
    except Exception as exc:  # pragma: no cover - runtime safety for health endpoint
        return {
            "ok": False,
            "database": None,
            "user": None,
            "postgres_version": None,
            "pgvector_enabled": False,
            "pgvector_version": None,
            "error": str(exc),
        }
