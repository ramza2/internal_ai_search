"""FastAPI dependencies for JWT auth (Step 19).

Existing business routes stay **unauthenticated** until a later
milestone wires these dependencies in. Admin-only routes use
``require_admin_user``.
"""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.rows import dict_row

from app.core.jwt_tokens import decode_access_token, parse_user_id_from_payload
from app.db.database import get_db_connection

security = HTTPBearer(auto_error=False)


class CurrentUserContext:
    """Row-shaped view of ``app_users`` for dependency consumers."""

    def __init__(self, row: dict) -> None:
        self.id = row["id"]
        self.login_id = row["login_id"]
        self.name = row.get("name")
        self.email = row.get("email")
        self.department = row.get("department")
        self.role = str(row.get("role") or "").upper()
        self.status = str(row.get("status") or "").upper()
        self.must_change_password = bool(row.get("must_change_password"))
        self.last_login_at = row.get("last_login_at")
        self.created_at = row.get("created_at")
        self.updated_at = row.get("updated_at")


_FETCH_USER_BY_ID = """
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


def _fetch_user_by_id(user_id) -> dict | None:
    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(_FETCH_USER_BY_ID, (user_id,))
            row = cur.fetchone()
    return dict(row) if row else None


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> CurrentUserContext:
    """Bearer JWT → ``app_users`` row. Missing/invalid token → 401."""
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        payload = decode_access_token(creds.credentials)
        uid = parse_user_id_from_payload(payload)
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from None

    row = _fetch_user_by_id(uid)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    st = str(row.get("status") or "").upper()
    if st != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )
    return CurrentUserContext(row)


async def require_active_user(
    user: Annotated[CurrentUserContext, Depends(get_current_user)],
) -> CurrentUserContext:
    """``ACTIVE`` users only (used by future protected routes)."""
    if user.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )
    return user


async def require_admin_user(
    user: Annotated[CurrentUserContext, Depends(get_current_user)],
) -> CurrentUserContext:
    """``ACTIVE`` + ``ADMIN`` — admin API gate."""
    if user.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )
    if user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required",
        )
    return user


__all__ = [
    "CurrentUserContext",
    "get_current_user",
    "require_active_user",
    "require_admin_user",
    "security",
]
