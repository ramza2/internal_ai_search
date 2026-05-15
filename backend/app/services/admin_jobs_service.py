"""Admin read-only APIs over ``scan_jobs`` / ``scan_failures`` (no worker)."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.db.database import get_db_connection
from app.services.action_log_service import sanitize_error_message
from app.services.scan_jobs_service import sanitize_job_params_for_response
from app.schemas.admin_pipeline_jobs import AdminJobChildItem, AdminJobChildrenResponse
from app.schemas.admin_jobs import (
    AdminJobDetailResponse,
    AdminJobFailureItem,
    AdminJobFailuresResponse,
    AdminJobItem,
    AdminJobListResponse,
)

logger = logging.getLogger(__name__)


def _parse_date(s: str | None) -> date | None:
    if not s or not str(s).strip():
        return None
    raw = str(s).strip()
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        return date.fromisoformat(raw)
    return None


def _start_of_day(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=UTC)


def _end_of_day(d: date) -> datetime:
    return datetime.combine(d, time(23, 59, 59, 999999), tzinfo=UTC)


def _build_job_where(
    *,
    data_source_id: UUID | None,
    status: str | None,
    job_type: str | None,
    parent_job_id: UUID | None,
    keyword: str | None,
    from_date: date | None,
    to_date: date | None,
) -> tuple[str, list[Any]]:
    """Returns SQL fragment ``(WHERE ... )`` inner part without WHERE keyword — actually returns AND-chained conditions."""
    parts: list[str] = ["TRUE"]
    params: list[Any] = []

    if data_source_id is not None:
        parts.append("sj.data_source_id = %s")
        params.append(data_source_id)
    if status and status.strip():
        parts.append("sj.status::text = %s")
        params.append(status.strip())
    if job_type and job_type.strip():
        parts.append("sj.job_type::text = %s")
        params.append(job_type.strip())
    if parent_job_id is not None:
        parts.append("sj.parent_job_id = %s")
        params.append(parent_job_id)
    if keyword and keyword.strip():
        kw = f"%{keyword.strip()}%"
        parts.append(
            "(COALESCE(ds.name, '') ILIKE %s OR "
            "COALESCE(sj.current_file_path, '') ILIKE %s OR "
            "COALESCE(sj.error_message, '') ILIKE %s)"
        )
        params.extend([kw, kw, kw])
    if from_date is not None:
        parts.append("sj.created_at >= %s")
        params.append(_start_of_day(from_date))
    if to_date is not None:
        parts.append("sj.created_at <= %s")
        params.append(_end_of_day(to_date))

    return " AND ".join(parts), params


_JOB_SELECT_CORE = """
    sj.id,
    sj.data_source_id,
    ds.name AS data_source_name,
    sj.job_type::text AS job_type,
    sj.status::text AS status,
    sj.started_at,
    sj.finished_at,
    ROUND(
        CASE
            WHEN sj.started_at IS NOT NULL AND sj.finished_at IS NOT NULL THEN
                EXTRACT(EPOCH FROM (sj.finished_at - sj.started_at)) * 1000
            WHEN sj.started_at IS NOT NULL AND sj.finished_at IS NULL
                 AND sj.status::text IN ('RUNNING', 'CANCELLING') THEN
                EXTRACT(EPOCH FROM (NOW() - sj.started_at)) * 1000
            ELSE NULL
        END
    )::bigint AS duration_ms,
    CASE
        WHEN sj.total_files IS NOT NULL AND sj.total_files > 0
             AND sj.processed_files IS NOT NULL THEN
            ROUND(100.0 * sj.processed_files::numeric / sj.total_files, 2)
        ELSE NULL
    END AS progress_percent,
    COALESCE(sj.total_files, 0)::int AS total_files,
    COALESCE(sj.processed_files, 0)::int AS processed_files,
    COALESCE(sj.completed_files, 0)::int AS completed_files,
    COALESCE(sj.failed_files, 0)::int AS failed_files,
    COALESCE(sj.skipped_files, 0)::int AS skipped_files,
    COALESCE(sj.deleted_files, 0)::int AS deleted_files,
    sj.current_file_path,
    sj.error_message,
    sj.requested_by,
    au.login_id AS requested_by_login_id,
    au.name AS requested_by_name,
    sj.created_at,
    sj.updated_at"""

_OPTIONAL_SCAN_JOB_FIELDS: list[tuple[str, str, str]] = [
    ("job_params", "sj.job_params", "NULL::jsonb AS job_params"),
    ("cancel_requested", "COALESCE(sj.cancel_requested, false) AS cancel_requested", "false AS cancel_requested"),
    ("worker_id", "sj.worker_id", "NULL::text AS worker_id"),
    ("heartbeat_at", "sj.heartbeat_at", "NULL::timestamptz AS heartbeat_at"),
    ("parent_job_id", "sj.parent_job_id", "NULL::uuid AS parent_job_id"),
    ("pipeline_step", "sj.pipeline_step", "NULL::text AS pipeline_step"),
    ("retry_count", "COALESCE(sj.retry_count, 0)::int AS retry_count", "0::int AS retry_count"),
    ("max_retries", "COALESCE(sj.max_retries, 1)::int AS max_retries", "1::int AS max_retries"),
    ("priority", "COALESCE(sj.priority, 0)::int AS priority", "0::int AS priority"),
]


def _fetch_scan_jobs_columns(cur: Any) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'scan_jobs'
        """
    )
    rows = cur.fetchall() or []
    return {str(r["column_name"]) for r in rows}


def _job_select_sql(cols: set[str]) -> str:
    parts = [_JOB_SELECT_CORE.strip()]
    for name, present_sql, absent_sql in _OPTIONAL_SCAN_JOB_FIELDS:
        parts.append(present_sql if name in cols else absent_sql)
    return ",\n    ".join(parts)


def _normalize_job_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    if "job_params" in out:
        out["job_params"] = sanitize_job_params_for_response(out.get("job_params"))
    return out


def list_admin_jobs(
    *,
    data_source_id: UUID | None,
    status: str | None,
    job_type: str | None,
    parent_job_id: UUID | None,
    keyword: str | None,
    from_date: str | None,
    to_date: str | None,
    limit: int,
    offset: int,
) -> AdminJobListResponse:
    warnings: list[str] = []
    fd = _parse_date(from_date)
    td = _parse_date(to_date)
    where_sql, params = _build_job_where(
        data_source_id=data_source_id,
        status=status,
        job_type=job_type,
        parent_job_id=parent_job_id,
        keyword=keyword,
        from_date=fd,
        to_date=td,
    )
    lim = max(1, min(int(limit), 200))
    off = max(0, int(offset))

    base_from = f"""
        FROM scan_jobs sj
        LEFT JOIN data_sources ds ON ds.id = sj.data_source_id
        LEFT JOIN app_users au ON au.id = sj.requested_by
        WHERE {where_sql}
    """

    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cols = _fetch_scan_jobs_columns(cur)
                sel = _job_select_sql(cols)

                cur.execute(f"SELECT COUNT(*) AS c {base_from}", params)
                crow = cur.fetchone() or {}
                total = int(crow.get("c") or 0)

                cur.execute(
                    f"SELECT {sel} {base_from} "
                    "ORDER BY sj.created_at DESC NULLS LAST, sj.started_at DESC NULLS LAST "
                    "LIMIT %s OFFSET %s",
                    [*params, lim, off],
                )
                rows = cur.fetchall() or []
    except psycopg.errors.UndefinedTable:
        logger.warning("admin jobs list: scan_jobs unavailable", exc_info=False)
        return AdminJobListResponse(
            total=0,
            items=[],
            warnings=["scan_jobs table is not available"],
            message="Job list is empty",
        )
    except psycopg.Error as exc:
        logger.warning("admin jobs list failed: %s", exc, exc_info=False)
        return AdminJobListResponse(
            total=0,
            items=[],
            warnings=[f"scan_jobs query failed: {type(exc).__name__}"],
            message="Job list is empty",
        )

    items = [AdminJobItem.model_validate(_normalize_job_row(dict(r))) for r in rows]
    msg = None
    if total == 0 and not warnings:
        msg = "Job list is empty"
    return AdminJobListResponse(total=total, items=items, warnings=warnings, message=msg)


def fetch_admin_job_detail(*, job_id: UUID) -> tuple[AdminJobDetailResponse | None, str | None]:
    """Return ``(detail, error_key)``. ``error_key`` is ``None`` on success, else
    ``not_found`` | ``scan_jobs_missing`` | ``db_error``.
    """
    warnings: list[str] = []
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cols = _fetch_scan_jobs_columns(cur)
                sel = _job_select_sql(cols)
                cur.execute(
                    f"SELECT {sel} "
                    """
                    FROM scan_jobs sj
                    LEFT JOIN data_sources ds ON ds.id = sj.data_source_id
                    LEFT JOIN app_users au ON au.id = sj.requested_by
                    WHERE sj.id = %s
                    """,
                    (job_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None, "not_found"

                failures_count = 0
                try:
                    cur.execute(
                        "SELECT COUNT(*) AS c FROM scan_failures WHERE scan_job_id = %s",
                        (job_id,),
                    )
                    fc = cur.fetchone() or {}
                    failures_count = int(fc.get("c") or 0)
                except psycopg.errors.UndefinedTable:
                    warnings.append("scan_failures table is not available")
                except psycopg.Error as exc:
                    logger.debug("failures count: %s", exc, exc_info=False)
                    warnings.append("Could not count scan_failures rows")

                job = AdminJobItem.model_validate(_normalize_job_row(dict(row)))
    except psycopg.errors.UndefinedTable:
        logger.warning("admin job detail: scan_jobs unavailable", exc_info=False)
        return None, "scan_jobs_missing"
    except psycopg.Error:
        logger.exception("admin job detail failed")
        return None, "db_error"

    return (
        AdminJobDetailResponse(
            job=job,
            failures_count=failures_count,
            warnings=warnings,
        ),
        None,
    )


def list_admin_job_children(*, parent_job_id: UUID) -> tuple[AdminJobChildrenResponse | None, str | None]:
    """Return direct child ``scan_jobs`` rows for a parent id (any parent job type)."""
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM scan_jobs WHERE id = %s", (parent_job_id,))
                if cur.fetchone() is None:
                    return None, "not_found"

                cols = _fetch_scan_jobs_columns(cur)
                sel = _job_select_sql(cols)
                cur.execute(
                    f"""
                    SELECT {sel}
                    FROM scan_jobs sj
                    LEFT JOIN data_sources ds ON ds.id = sj.data_source_id
                    LEFT JOIN app_users au ON au.id = sj.requested_by
                    WHERE sj.parent_job_id = %s
                    ORDER BY sj.created_at ASC NULLS LAST, sj.started_at ASC NULLS LAST
                    """,
                    (parent_job_id,),
                )
                rows = cur.fetchall() or []
    except psycopg.errors.UndefinedTable:
        return None, "scan_jobs_missing"
    except psycopg.Error:
        logger.exception("list_admin_job_children failed")
        return None, "db_error"

    items: list[AdminJobChildItem] = []
    for r in rows:
        row = _normalize_job_row(dict(r))
        items.append(
            AdminJobChildItem(
                id=row["id"],
                job_type=str(row.get("job_type") or ""),
                pipeline_step=row.get("pipeline_step"),
                status=str(row.get("status") or ""),
                started_at=row.get("started_at"),
                finished_at=row.get("finished_at"),
                progress_percent=row.get("progress_percent"),
            )
        )
    return AdminJobChildrenResponse(parent_job_id=parent_job_id, items=items, total=len(items)), None


def list_admin_job_failures(
    *,
    job_id: UUID,
    limit: int,
    offset: int,
) -> tuple[AdminJobFailuresResponse | None, str | None]:
    """Returns (response, error_message). ``None`` response + message when job missing."""
    lim = max(1, min(int(limit), 500))
    off = max(0, int(offset))
    warnings: list[str] = []

    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM scan_jobs WHERE id = %s", (job_id,))
                if cur.fetchone() is None:
                    return None, "Job not found"
    except psycopg.errors.UndefinedTable:
        return (
            AdminJobFailuresResponse(
                job_id=job_id,
                total=0,
                items=[],
                warnings=["scan_jobs table is not available"],
            ),
            None,
        )
    except psycopg.Error as exc:
        return None, str(exc)

    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS c FROM scan_failures WHERE scan_job_id = %s",
                    (job_id,),
                )
                total = int((cur.fetchone() or {}).get("c") or 0)
                cur.execute(
                    """
                    SELECT id, file_id, remote_path, error_code::text AS error_code,
                           error_message, created_at
                    FROM scan_failures
                    WHERE scan_job_id = %s
                    ORDER BY created_at DESC NULLS LAST
                    LIMIT %s OFFSET %s
                    """,
                    (job_id, lim, off),
                )
                rows = cur.fetchall() or []
    except psycopg.errors.UndefinedTable:
        warnings.append("scan_failures table is not available")
        return AdminJobFailuresResponse(job_id=job_id, total=0, items=[], warnings=warnings), None
    except psycopg.Error as exc:
        logger.warning("list job failures: %s", exc, exc_info=False)
        return None, str(exc)

    items: list[AdminJobFailureItem] = []
    for r in rows:
        row = dict(r)
        row["error_message"] = sanitize_error_message(row.get("error_message"))
        items.append(AdminJobFailureItem.model_validate(row))
    return AdminJobFailuresResponse(job_id=job_id, total=total, items=items, warnings=warnings), None


__all__ = [
    "fetch_admin_job_detail",
    "list_admin_job_children",
    "list_admin_job_failures",
    "list_admin_jobs",
]
