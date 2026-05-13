"""Signup, login, password change (Step 19)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import errors as pg_errors
from psycopg.rows import dict_row

from app.core.config import settings
from app.core.jwt_tokens import create_access_token
from app.core.password import hash_password, verify_password
from app.db.database import get_db_connection

_LOGIN_ID_RE = re.compile(r"^[a-zA-Z0-9_]{3,64}$")


@dataclass(frozen=True)
class AuthServiceError(Exception):
    status_code: int
    message: str


def _validate_password(plain: str) -> None:
    ml = int(settings.password_min_length)
    if len(plain) < ml:
        raise AuthServiceError(
            400, f"Password must be at least {ml} characters"
        )
    if len(plain.encode("utf-8")) > 72:
        raise AuthServiceError(400, "Password is too long (max 72 bytes)")


def _validate_signup_fields(
    login_id: str,
    name: str,
    email: str,
    department: str | None,
) -> None:
    lid = login_id.strip()
    if not _LOGIN_ID_RE.match(lid):
        raise AuthServiceError(
            400,
            "login_id must be 3–64 characters: letters, digits, underscore only",
        )
    if not name or not name.strip():
        raise AuthServiceError(400, "name is required")
    em = email.strip()
    if not em or "@" not in em or len(em) > 254:
        raise AuthServiceError(400, "valid email is required")


_FETCH_BY_LOGIN = """
    SELECT
        id,
        login_id,
        password_hash,
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
    WHERE login_id = %s
"""

_FETCH_BY_ID = """
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

_INSERT_USER = """
    INSERT INTO app_users (
        id, login_id, password_hash, name, email, department,
        role, status, must_change_password, last_login_at, created_at, updated_at
    ) VALUES (
        %s, %s, %s, %s, %s, %s,
        'USER'::user_role,
        'PENDING'::user_status,
        FALSE,
        NULL, NOW(), NOW()
    )
"""

_UPDATE_LAST_LOGIN = """
    UPDATE app_users SET last_login_at = NOW(), updated_at = NOW() WHERE id = %s
"""

_UPDATE_PASSWORD = """
    UPDATE app_users
    SET password_hash = %s,
        must_change_password = FALSE,
        updated_at = NOW()
    WHERE id = %s
"""


def user_public_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Strip secrets — safe for JSON responses."""
    return {
        "id": str(row["id"]),
        "login_id": row["login_id"],
        "name": row.get("name"),
        "email": row.get("email"),
        "department": row.get("department"),
        "role": str(row.get("role") or "").upper(),
        "status": str(row.get("status") or "").upper(),
        "must_change_password": bool(row.get("must_change_password")),
        "last_login_at": row.get("last_login_at").isoformat()
        if row.get("last_login_at")
        else None,
        "created_at": row.get("created_at").isoformat()
        if row.get("created_at")
        else None,
        "updated_at": row.get("updated_at").isoformat()
        if row.get("updated_at")
        else None,
    }


def signup(
    *,
    login_id: str,
    password: str,
    name: str,
    email: str,
    department: str | None,
) -> dict[str, Any]:
    _validate_password(password)
    _validate_signup_fields(login_id, name, email, department)
    uid = uuid.uuid4()
    ph = hash_password(password)
    dept = (department or "").strip() or None
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _INSERT_USER,
                    (
                        uid,
                        login_id.strip(),
                        ph,
                        name.strip(),
                        email.strip(),
                        dept,
                    ),
                )
            conn.commit()
    except pg_errors.UniqueViolation as exc:
        raise AuthServiceError(409, "login_id is already taken") from exc
    except pg_errors.UndefinedTable as exc:
        raise AuthServiceError(
            500, "Database schema error: app_users table missing"
        ) from exc
    except psycopg.Error as exc:
        raise AuthServiceError(500, f"Database error: {type(exc).__name__}") from exc

    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(_FETCH_BY_ID, (uid,))
            row = cur.fetchone()
    if not row:
        raise AuthServiceError(500, "User created but could not be reloaded")
    return user_public_dict(dict(row))


def login(*, login_id: str, password: str) -> dict[str, Any]:
    lid = (login_id or "").strip()
    if not lid:
        raise AuthServiceError(401, "Invalid login_id or password")

    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(_FETCH_BY_LOGIN, (lid,))
            row = cur.fetchone()

    if not row or not verify_password(password, row.get("password_hash") or ""):
        raise AuthServiceError(401, "Invalid login_id or password")

    st = str(row.get("status") or "").upper()
    if st == "PENDING":
        raise AuthServiceError(403, "Account is pending approval")
    if st == "INACTIVE":
        raise AuthServiceError(403, "Account is inactive")
    if st == "LOCKED":
        raise AuthServiceError(403, "Account is locked")
    if st != "ACTIVE":
        raise AuthServiceError(403, "Account is inactive")

    uid = row["id"]
    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(_UPDATE_LAST_LOGIN, (uid,))
            cur.execute(_FETCH_BY_ID, (uid,))
            row2 = cur.fetchone()
        conn.commit()
    if not row2:
        raise AuthServiceError(500, "Login state could not be reloaded")
    pub = user_public_dict(dict(row2))
    token = create_access_token(str(uid))
    user_out = {
        "id": pub["id"],
        "login_id": pub["login_id"],
        "name": pub["name"],
        "email": pub["email"],
        "department": pub["department"],
        "role": pub["role"],
        "status": pub["status"],
        "must_change_password": pub["must_change_password"],
    }
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_minutes": int(settings.jwt_access_token_expire_minutes),
        "user": user_out,
    }


def me_dict(*, user_id: uuid.UUID) -> dict[str, Any]:
    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(_FETCH_BY_ID, (user_id,))
            row = cur.fetchone()
    if not row:
        raise AuthServiceError(401, "User not found")
    return user_public_dict(dict(row))


def change_password(
    *, user_id: uuid.UUID, current_password: str, new_password: str
) -> None:
    _validate_password(new_password)
    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password_hash FROM app_users WHERE id = %s", (user_id,)
            )
            row = cur.fetchone()
    if not row:
        raise AuthServiceError(401, "User not found")
    if not verify_password(current_password, row.get("password_hash") or ""):
        raise AuthServiceError(401, "Invalid current password")

    ph = hash_password(new_password)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_UPDATE_PASSWORD, (ph, user_id))
        conn.commit()


__all__ = [
    "AuthServiceError",
    "change_password",
    "login",
    "me_dict",
    "signup",
    "user_public_dict",
]
