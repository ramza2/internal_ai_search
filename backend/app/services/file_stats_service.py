"""Aggregate ``files`` table metadata into dashboard-friendly statistics.

All grouping/aggregation runs in SQL (``COUNT``, ``SUM``, ``GROUP BY`` with
``FILTER (WHERE ...)``); Python never materializes the entire ``files`` table.
The top-N largest files use ``ORDER BY size_bytes DESC LIMIT 10``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from app.db.database import get_db_connection
from app.services.data_source_service import DataSourceNotFound
from app.utils.file_type import FILE_TYPE_CASE_SQL, humanize_bytes


SUCCESS_MESSAGE = "File statistics retrieved successfully"

_TOP_LARGEST_LIMIT = 10
_NONE_EXTENSION_LABEL = "(none)"


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _scope_filters(
    *, ds_id: UUID | None, include_deleted: bool, alias: str
) -> tuple[str, list[Any]]:
    """Build ``WHERE`` fragment + bound params for the requested scope.

    ``alias`` is the SQL table reference, e.g. ``"f"`` or ``"files"``; it must
    be a fixed internal token (never user input). Returns ``("TRUE", [])``
    when no filters apply.
    """
    parts: list[str] = []
    params: list[Any] = []
    if ds_id is not None:
        parts.append(f"{alias}.data_source_id = %s")
        params.append(ds_id)
    if not include_deleted:
        parts.append(f"{alias}.analysis_status <> 'DELETED'::analysis_status")
    return (" AND ".join(parts) if parts else "TRUE"), params


def _fetch_scope(
    cur, ds_id: UUID | None
) -> dict[str, Any]:
    """Look up the data source (when scoped) and produce the response ``scope``."""
    if ds_id is None:
        return {
            "data_source_id": None,
            "data_source_name": "ALL",
            "source_type": "ALL",
        }
    cur.execute(
        """
        SELECT id, name, source_type::text AS source_type
        FROM data_sources
        WHERE id = %s
        """,
        (ds_id,),
    )
    row = cur.fetchone()
    if not row:
        raise DataSourceNotFound()
    return {
        "data_source_id": str(row["id"]),
        "data_source_name": row["name"],
        "source_type": row["source_type"],
    }


def _fetch_summary(
    cur, *, ds_id: UUID | None, include_deleted: bool
) -> dict[str, Any]:
    where_sql, params = _scope_filters(
        ds_id=ds_id, include_deleted=include_deleted, alias="f"
    )
    sql = f"""
        SELECT
            COUNT(*)::bigint AS total_items,
            COUNT(*) FILTER (WHERE NOT f.is_directory)::bigint AS total_files,
            COUNT(*) FILTER (WHERE f.is_directory)::bigint AS total_directories,
            COALESCE(
                SUM(f.size_bytes) FILTER (WHERE NOT f.is_directory),
                0
            )::bigint AS total_size_bytes,
            MAX(f.last_modified) AS latest_modified_at
        FROM files AS f
        WHERE {where_sql}
    """
    cur.execute(sql, params)
    row = cur.fetchone() or {}

    if ds_id is None:
        cur.execute(
            "SELECT MAX(last_scan_at) AS last_synced_at FROM data_sources"
        )
        scan_row = cur.fetchone() or {}
    else:
        cur.execute(
            "SELECT last_scan_at AS last_synced_at FROM data_sources WHERE id = %s",
            (ds_id,),
        )
        scan_row = cur.fetchone() or {}

    total_size = int(row.get("total_size_bytes") or 0)
    return {
        "total_items": int(row.get("total_items") or 0),
        "total_files": int(row.get("total_files") or 0),
        "total_directories": int(row.get("total_directories") or 0),
        "total_size_bytes": total_size,
        "total_size_human": humanize_bytes(total_size),
        "latest_modified_at": _iso(row.get("latest_modified_at")),
        "last_synced_at": _iso(scan_row.get("last_synced_at")),
    }


def _fetch_by_analysis_status(
    cur, *, ds_id: UUID | None, include_deleted: bool
) -> list[dict[str, Any]]:
    where_sql, params = _scope_filters(
        ds_id=ds_id, include_deleted=include_deleted, alias="f"
    )
    sql = f"""
        SELECT
            f.analysis_status::text AS status,
            COUNT(*)::bigint AS count
        FROM files AS f
        WHERE {where_sql}
        GROUP BY f.analysis_status
        ORDER BY count DESC, status ASC
    """
    cur.execute(sql, params)
    return [
        {"status": r["status"], "count": int(r["count"])}
        for r in cur.fetchall()
    ]


def _fetch_by_extension(
    cur, *, ds_id: UUID | None, include_deleted: bool
) -> list[dict[str, Any]]:
    where_sql, params = _scope_filters(
        ds_id=ds_id, include_deleted=include_deleted, alias="f"
    )
    file_type_case = FILE_TYPE_CASE_SQL.replace("extension", "f.extension")
    sql = f"""
        SELECT
            lower(nullif(trim(f.extension), '')) AS ext_norm,
            ({file_type_case}) AS file_type,
            COUNT(*)::bigint AS count,
            COALESCE(SUM(f.size_bytes), 0)::bigint AS total_size_bytes
        FROM files AS f
        WHERE {where_sql} AND NOT f.is_directory
        GROUP BY ext_norm, file_type
        ORDER BY count DESC, ext_norm ASC NULLS LAST
    """
    cur.execute(sql, params)
    out: list[dict[str, Any]] = []
    for r in cur.fetchall():
        ext = r.get("ext_norm")
        out.append(
            {
                "extension": ext if ext else _NONE_EXTENSION_LABEL,
                "count": int(r["count"]),
                "total_size_bytes": int(r["total_size_bytes"]),
                "file_type": r["file_type"],
            }
        )
    return out


def _fetch_by_file_type(
    cur, *, ds_id: UUID | None, include_deleted: bool
) -> list[dict[str, Any]]:
    where_sql, params = _scope_filters(
        ds_id=ds_id, include_deleted=include_deleted, alias="f"
    )
    file_type_case = FILE_TYPE_CASE_SQL.replace("extension", "f.extension")
    sql = f"""
        SELECT
            ({file_type_case}) AS file_type,
            COUNT(*)::bigint AS count,
            COALESCE(SUM(f.size_bytes), 0)::bigint AS total_size_bytes
        FROM files AS f
        WHERE {where_sql} AND NOT f.is_directory
        GROUP BY file_type
        ORDER BY count DESC, file_type ASC
    """
    cur.execute(sql, params)
    return [
        {
            "file_type": r["file_type"],
            "count": int(r["count"]),
            "total_size_bytes": int(r["total_size_bytes"]),
        }
        for r in cur.fetchall()
    ]


def _fetch_top_largest(
    cur, *, ds_id: UUID | None, include_deleted: bool
) -> list[dict[str, Any]]:
    where_sql, params = _scope_filters(
        ds_id=ds_id, include_deleted=include_deleted, alias="f"
    )
    sql = f"""
        SELECT
            f.id, f.filename, f.remote_path, f.extension,
            f.size_bytes, f.last_modified
        FROM files AS f
        WHERE {where_sql}
            AND NOT f.is_directory
            AND f.size_bytes IS NOT NULL
        ORDER BY f.size_bytes DESC NULLS LAST, f.filename ASC
        LIMIT %s
    """
    cur.execute(sql, [*params, _TOP_LARGEST_LIMIT])
    rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        size = int(r["size_bytes"]) if r.get("size_bytes") is not None else None
        out.append(
            {
                "id": str(r["id"]),
                "filename": r["filename"],
                "remote_path": r["remote_path"],
                "extension": r["extension"],
                "size_bytes": size,
                "size_human": humanize_bytes(size),
                "last_modified": _iso(r.get("last_modified")),
            }
        )
    return out


def _fetch_by_data_source(
    cur, *, include_deleted: bool
) -> list[dict[str, Any]]:
    deleted_filter = (
        "" if include_deleted else " AND f.analysis_status <> 'DELETED'::analysis_status"
    )
    sql = f"""
        SELECT
            d.id,
            d.name,
            d.source_type::text AS source_type,
            d.last_scan_at,
            COUNT(f.id) FILTER (WHERE f.id IS NOT NULL AND NOT f.is_directory)::bigint
                AS total_files,
            COUNT(f.id) FILTER (WHERE f.id IS NOT NULL AND f.is_directory)::bigint
                AS total_directories,
            COALESCE(
                SUM(f.size_bytes) FILTER (WHERE NOT f.is_directory),
                0
            )::bigint AS total_size_bytes
        FROM data_sources AS d
        LEFT JOIN files AS f
               ON f.data_source_id = d.id{deleted_filter}
        GROUP BY d.id, d.name, d.source_type, d.last_scan_at, d.created_at
        ORDER BY total_files DESC, d.created_at DESC NULLS LAST, d.id ASC
    """
    cur.execute(sql)
    return [
        {
            "data_source_id": str(r["id"]),
            "data_source_name": r["name"],
            "source_type": r["source_type"],
            "total_files": int(r["total_files"]),
            "total_directories": int(r["total_directories"]),
            "total_size_bytes": int(r["total_size_bytes"]),
            "last_scan_at": _iso(r.get("last_scan_at")),
        }
        for r in cur.fetchall()
    ]


def get_file_statistics(
    *,
    data_source_id: UUID | None,
    include_deleted: bool,
) -> dict[str, Any]:
    """Compose the file-stats response payload (raises ``DataSourceNotFound``
    when a scoped ``data_source_id`` does not exist)."""
    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            scope = _fetch_scope(cur, data_source_id)
            summary = _fetch_summary(
                cur, ds_id=data_source_id, include_deleted=include_deleted
            )
            by_status = _fetch_by_analysis_status(
                cur, ds_id=data_source_id, include_deleted=include_deleted
            )
            by_extension = _fetch_by_extension(
                cur, ds_id=data_source_id, include_deleted=include_deleted
            )
            by_file_type = _fetch_by_file_type(
                cur, ds_id=data_source_id, include_deleted=include_deleted
            )
            top_largest = _fetch_top_largest(
                cur, ds_id=data_source_id, include_deleted=include_deleted
            )
            by_data_source: list[dict[str, Any]] | None = None
            if data_source_id is None:
                by_data_source = _fetch_by_data_source(
                    cur, include_deleted=include_deleted
                )

    payload: dict[str, Any] = {
        "status": "ok",
        "scope": scope,
        "summary": summary,
        "by_analysis_status": by_status,
        "by_extension": by_extension,
        "by_file_type": by_file_type,
        "top_largest_files": top_largest,
        "message": SUCCESS_MESSAGE,
    }
    if by_data_source is not None:
        payload["by_data_source"] = by_data_source
    return payload
