"""Best-effort audit logging to ``action_logs`` (Step 20).

Failures are swallowed — callers' API responses must never depend on log
writes succeeding.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, date, datetime, time
from typing import Any

import psycopg
from fastapi import Request
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.core.request_context import get_request_audit_meta
from app.db.database import get_db_connection

logger = logging.getLogger(__name__)

_INSERT_SQL = """
    INSERT INTO action_logs (
        id,
        user_id,
        action_type,
        result,
        request_url,
        request_method,
        search_query,
        data_source_id,
        target_file_id,
        target_file_path,
        ip_address,
        user_agent,
        detail,
        error_message,
        created_at
    ) VALUES (
        %s, %s, %s, %s::action_result, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
    )
"""

_DETAIL_KEY_DENY = frozenset(
    {
        "password",
        "current_password",
        "new_password",
        "password_hash",
        "credential_secret",
        "credential_secret_enc",
        "access_token",
        "authorization",
        "chunk_text",
        "extracted_text",
        "prompt",
        "messages",
        "answer",
        "text",
        "lines",
        "highlights",
        "preview",
    }
)

_SENSITIVE_ERR_PATTERNS = re.compile(
    r"(password|secret|token|bearer|credential|authorization|api[_-]?key)",
    re.IGNORECASE,
)


def sanitize_error_message(msg: str | None, *, max_len: int = 500) -> str | None:
    """Strip obvious sensitive substrings from persisted error text."""
    if not msg:
        return None
    s = str(msg).strip()
    if not s:
        return None
    if len(s) > max_len:
        s = s[:max_len] + "…"
    if _SENSITIVE_ERR_PATTERNS.search(s):
        return "Error details redacted"
    return s


def redact_detail(value: Any) -> Any:
    """Recursively remove denied keys and truncate huge strings."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            lk = str(k).lower()
            if lk in _DETAIL_KEY_DENY:
                continue
            out[str(k)] = redact_detail(v)
        return out
    if isinstance(value, list):
        return [redact_detail(v) for v in value[:200]]
    if isinstance(value, str) and len(value) > 2000:
        return value[:2000] + "…"
    return value


def write_action_log(
    *,
    user_id: uuid.UUID | None,
    action_type: str,
    result: str,
    request: Request | None,
    search_query: str | None = None,
    data_source_id: uuid.UUID | None = None,
    target_file_id: uuid.UUID | None = None,
    target_file_path: str | None = None,
    detail: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    """Insert one row; raises only on unexpected programmer error (avoid in callers)."""
    ip, ua, url, method = (None, None, "", "")
    if request is not None:
        ip, ua, url, method = get_request_audit_meta(request)
    safe_detail = redact_detail(detail) if detail else None
    if isinstance(safe_detail, dict):
        safe_detail = dict(safe_detail)
    err = sanitize_error_message(error_message)
    sq = search_query
    if sq is not None and len(sq) > 4000:
        sq = sq[:4000] + "…"
    tpath = target_file_path
    if tpath is not None and len(tpath) > 4000:
        tpath = tpath[:4000] + "…"

    log_id = uuid.uuid4()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                _INSERT_SQL,
                (
                    log_id,
                    user_id,
                    action_type[:128],
                    result.upper(),
                    url or None,
                    method[:16] if method else None,
                    sq,
                    data_source_id,
                    target_file_id,
                    tpath,
                    ip,
                    ua,
                    Json(safe_detail) if safe_detail is not None else None,
                    err,
                ),
            )
        conn.commit()


def write_action_log_safe(
    *,
    user_id: uuid.UUID | None,
    action_type: str,
    result: str,
    request: Request | None,
    search_query: str | None = None,
    data_source_id: uuid.UUID | None = None,
    target_file_id: uuid.UUID | None = None,
    target_file_path: str | None = None,
    detail: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    """Like :func:`write_action_log` but never propagates DB errors."""
    try:
        write_action_log(
            user_id=user_id,
            action_type=action_type,
            result=result,
            request=request,
            search_query=search_query,
            data_source_id=data_source_id,
            target_file_id=target_file_id,
            target_file_path=target_file_path,
            detail=detail,
            error_message=error_message,
        )
    except psycopg.errors.UndefinedTable:
        logger.debug("action_logs skipped: table missing", exc_info=False)
    except psycopg.Error as exc:
        logger.debug("action_logs insert failed: %s", type(exc).__name__, exc_info=False)
    except Exception as exc:  # pragma: no cover
        logger.debug("action_logs insert failed: %s", type(exc).__name__, exc_info=True)


def _parse_bound(
    raw: str | None,
    *,
    end_of_day: bool,
) -> datetime | None:
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        d = date.fromisoformat(s)
        if end_of_day:
            return datetime.combine(d, time(23, 59, 59, 999999), tzinfo=UTC)
        return datetime.combine(d, time.min, tzinfo=UTC)
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def list_action_logs(
    *,
    user_id: uuid.UUID | None,
    action_type: str | None,
    result: str | None,
    data_source_id: uuid.UUID | None,
    target_file_id: uuid.UUID | None,
    keyword: str | None,
    from_date: str | None,
    to_date: str | None,
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, Any]]]:
    """Return ``(total, rows)`` for admin audit UI. Raises on DB errors."""
    clauses: list[str] = ["1=1"]
    params: list[Any] = []

    def add(sql: str, val: Any) -> None:
        params.append(val)
        clauses.append(sql.format(n=len(params)))

    if user_id is not None:
        add("l.user_id = %s", user_id)
    if action_type:
        params.append(action_type.strip())
        clauses.append(f"l.action_type = %s")
    if result:
        params.append(result.strip().upper())
        clauses.append("l.result = %s::action_result")
    if data_source_id is not None:
        add("l.data_source_id = %s", data_source_id)
    if target_file_id is not None:
        add("l.target_file_id = %s", target_file_id)

    fd = _parse_bound(from_date, end_of_day=False)
    if fd is not None:
        add("l.created_at >= %s", fd)
    td = _parse_bound(to_date, end_of_day=True)
    if td is not None:
        add("l.created_at <= %s", td)

    kw = (keyword or "").strip()
    if kw:
        pat = f"%{kw}%"
        params.extend([pat, pat, pat])
        clauses.append(
            "(l.search_query ILIKE %s OR l.target_file_path ILIKE %s OR l.detail::text ILIKE %s)"
        )

    where_sql = " AND ".join(clauses)

    count_sql = f"SELECT COUNT(*)::int AS c FROM action_logs l WHERE {where_sql}"
    list_sql = f"""
        SELECT
            l.id,
            l.user_id,
            u.login_id,
            u.name AS user_name,
            u.role::text AS user_role,
            l.action_type,
            l.result::text AS result,
            l.request_url,
            l.request_method,
            l.search_query,
            l.data_source_id,
            l.target_file_id,
            l.target_file_path,
            l.ip_address,
            l.user_agent,
            l.detail,
            l.error_message,
            l.created_at
        FROM action_logs l
        LEFT JOIN app_users u ON u.id = l.user_id
        WHERE {where_sql}
        ORDER BY l.created_at DESC
        LIMIT %s OFFSET %s
    """

    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(count_sql, params)
            crow = cur.fetchone()
            total = int(crow["c"]) if crow else 0
            cur.execute(list_sql, params + [limit, offset])
            rows = [dict(r) for r in cur.fetchall()]

    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": str(r["id"]),
                "user_id": str(r["user_id"]) if r.get("user_id") else None,
                "login_id": r.get("login_id"),
                "user_name": r.get("user_name"),
                "user_role": str(r["user_role"]).upper() if r.get("user_role") else None,
                "action_type": r.get("action_type"),
                "result": r.get("result"),
                "request_url": r.get("request_url"),
                "request_method": r.get("request_method"),
                "search_query": r.get("search_query"),
                "data_source_id": str(r["data_source_id"]) if r.get("data_source_id") else None,
                "target_file_id": str(r["target_file_id"]) if r.get("target_file_id") else None,
                "target_file_path": r.get("target_file_path"),
                "ip_address": r.get("ip_address"),
                "user_agent": r.get("user_agent"),
                "detail": r.get("detail"),
                "error_message": r.get("error_message"),
                "created_at": r["created_at"].isoformat()
                if r.get("created_at")
                else None,
            }
        )
    return total, out


__all__ = [
    "list_action_logs",
    "redact_detail",
    "sanitize_error_message",
    "write_action_log",
    "write_action_log_safe",
]
