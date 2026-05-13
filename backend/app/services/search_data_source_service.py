"""Read-only listing of active ``data_sources`` for search / RAG UI filters.

Exposes only non-sensitive columns (no URLs, paths, usernames, credentials,
or internal connection error text). Used by ``GET /api/search/data-sources``.

TODO: When multi-tenant customers need it, add per-user ``data_source`` ACL
filtering in SQL (keep this module as the single place for that policy).
"""

from __future__ import annotations

from psycopg.rows import dict_row

from app.db.database import get_db_connection
from app.schemas.search import SearchDataSourceListResponse, SearchDataSourcePublic


class SearchDataSourcesQueryError(Exception):
    """Raised when the safe listing query cannot be completed."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


_SQL = """
    SELECT
        id,
        name,
        source_type::text AS source_type,
        description,
        last_scan_at,
        last_connection_success
    FROM data_sources
    WHERE is_active = %s
    ORDER BY COALESCE(last_scan_at, 'epoch'::timestamptz) DESC, name ASC
"""


def list_search_data_sources_public(*, is_active: bool = True) -> SearchDataSourceListResponse:
    """Return active sources ordered by ``last_scan_at`` (desc), then ``name`` (asc)."""
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(_SQL, (is_active,))
                rows = cur.fetchall()
    except Exception as exc:
        raise SearchDataSourcesQueryError(str(exc)) from exc

    items: list[SearchDataSourcePublic] = []
    for row in rows or []:
        items.append(
            SearchDataSourcePublic(
                id=row["id"],
                name=row["name"],
                source_type=str(row["source_type"]),
                description=row.get("description"),
                last_scan_at=row.get("last_scan_at"),
                last_connection_success=row.get("last_connection_success"),
            )
        )
    return SearchDataSourceListResponse(
        status="ok",
        items=items,
        total=len(items),
        message="Search data sources retrieved successfully",
    )
