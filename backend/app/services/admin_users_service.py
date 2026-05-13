"""Admin-only ``app_users`` maintenance (Step 19)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.db.database import get_db_connection
from app.services.auth_service import user_public_dict

_FETCH_USER = """
    SELECT
        id,
        login_id,
        name,
        email,
        department,
        role::text AS role,
        status::text AS status,
        must_change_password,
        last_login_at,
        created_at,
        updated_at
    FROM app_users
    WHERE id = %s
"""

_COUNT_OTHER_ACTIVE_ADMINS = """
    SELECT COUNT(*)::int AS c
    FROM app_users
    WHERE role::text = 'ADMIN'
      AND status::text = 'ACTIVE'
      AND id <> %s
"""


@dataclass(frozen=True)
class AdminUsersError(Exception):
    status_code: int
    message: str


def _fetch(uid: uuid.UUID) -> dict[str, Any] | None:
    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(_FETCH_USER, (uid,))
            row = cur.fetchone()
    return dict(row) if row else None


def _count_other_active_admins(exclude_id: uuid.UUID) -> int:
    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(_COUNT_OTHER_ACTIVE_ADMINS, (exclude_id,))
            row = cur.fetchone()
    return int(row["c"]) if row else 0


def _guard_last_active_admin(target: dict[str, Any], _op: str) -> None:
    """Block demotion / lock / deactivate when ``target`` is the sole ``ACTIVE`` ``ADMIN``."""
    role = str(target.get("role") or "").upper()
    status = str(target.get("status") or "").upper()
    if role != "ADMIN" or status != "ACTIVE":
        return
    if _count_other_active_admins(target["id"]) < 1:
        raise AdminUsersError(
            400,
            "Cannot remove the last active administrator from the system",
        )


def list_users(
    *,
    status: str | None,
    role: str | None,
    keyword: str | None,
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, Any]]]:
    clauses: list[str] = ["TRUE"]
    params: list[Any] = []
    if status:
        clauses.append("status::text = %s")
        params.append(status.strip().upper())
    if role:
        clauses.append("role::text = %s")
        params.append(role.strip().upper())
    if keyword and keyword.strip():
        kw = f"%{keyword.strip()}%"
        clauses.append(
            "(login_id ILIKE %s OR name ILIKE %s OR COALESCE(email,'') ILIKE %s)"
        )
        params.extend([kw, kw, kw])

    where_sql = " AND ".join(clauses)
    count_sql = f"SELECT COUNT(*)::int AS c FROM app_users WHERE {where_sql}"
    list_sql = f"""
        SELECT
            id,
            login_id,
            name,
            email,
            department,
            role::text AS role,
            status::text AS status,
            must_change_password,
            last_login_at,
            created_at,
            updated_at
        FROM app_users
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(count_sql, tuple(params))
                total = int(cur.fetchone()["c"])
                cur.execute(
                    list_sql,
                    tuple(params + [limit, offset]),
                )
                rows = cur.fetchall()
    except psycopg.Error as exc:
        raise AdminUsersError(500, f"Database error: {type(exc).__name__}") from exc

    items = [user_public_dict(dict(r)) for r in rows]
    return total, items


def _update_status(uid: uuid.UUID, new_status: str) -> dict[str, Any]:
    row = _fetch(uid)
    if not row:
        raise AdminUsersError(404, "User not found")
    new_st = new_status.upper()
    if new_st == "INACTIVE" or new_st == "LOCKED":
        _guard_last_active_admin(row, new_st)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE app_users
                    SET status = %s::user_status,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (new_st, uid),
                )
            conn.commit()
    except psycopg.Error as exc:
        raise AdminUsersError(500, f"Database error: {type(exc).__name__}") from exc
    out = _fetch(uid)
    if not out:
        raise AdminUsersError(500, "User could not be reloaded")
    return user_public_dict(out)


def approve_user(uid: uuid.UUID) -> dict[str, Any]:
    return _update_status(uid, "ACTIVE")


def deactivate_user(uid: uuid.UUID) -> dict[str, Any]:
    return _update_status(uid, "INACTIVE")


def lock_user(uid: uuid.UUID) -> dict[str, Any]:
    return _update_status(uid, "LOCKED")


def activate_user(uid: uuid.UUID) -> dict[str, Any]:
    row = _fetch(uid)
    if not row:
        raise AdminUsersError(404, "User not found")
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE app_users
                    SET status = 'ACTIVE'::user_status,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (uid,),
                )
            conn.commit()
    except psycopg.Error as exc:
        raise AdminUsersError(500, f"Database error: {type(exc).__name__}") from exc
    out = _fetch(uid)
    if not out:
        raise AdminUsersError(500, "User could not be reloaded")
    return user_public_dict(out)


def set_user_role(uid: uuid.UUID, new_role: str) -> dict[str, Any]:
    nr = new_role.strip().upper()
    if nr not in ("USER", "ADMIN"):
        raise AdminUsersError(400, "role must be USER or ADMIN")

    row = _fetch(uid)
    if not row:
        raise AdminUsersError(404, "User not found")
    old_role = str(row.get("role") or "").upper()
    if old_role == "ADMIN" and nr == "USER":
        _guard_last_active_admin(row, "demote")

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE app_users
                    SET role = %s::user_role,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (nr, uid),
                )
            conn.commit()
    except psycopg.Error as exc:
        raise AdminUsersError(500, f"Database error: {type(exc).__name__}") from exc
    out = _fetch(uid)
    if not out:
        raise AdminUsersError(500, "User could not be reloaded")
    return user_public_dict(out)


__all__ = [
    "AdminUsersError",
    "activate_user",
    "approve_user",
    "deactivate_user",
    "list_users",
    "lock_user",
    "set_user_role",
]
