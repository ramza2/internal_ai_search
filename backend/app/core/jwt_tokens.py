"""JWT access tokens (HS256) for Step 19 auth.

Named ``jwt_tokens`` (not ``jwt``) so ``import jwt`` always resolves to the
**PyJWT** distribution, not this module.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from jwt import InvalidTokenError

from app.core.config import settings


def create_access_token(
    subject: str,
    *,
    expires_delta_minutes: int | None = None,
) -> str:
    """Encode a JWT with ``sub`` = user id (UUID string).

    ``exp`` is UTC. Uses ``settings.jwt_secret_key`` and
    ``settings.jwt_algorithm``.
    """
    minutes = (
        expires_delta_minutes
        if expires_delta_minutes is not None
        else int(settings.jwt_access_token_expire_minutes)
    )
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": now + timedelta(minutes=minutes),
        "type": "access",
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises :class:`jwt.InvalidTokenError` on failure."""
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )


def parse_user_id_from_payload(payload: dict[str, Any]) -> UUID:
    """Extract ``sub`` as UUID or raise ``InvalidTokenError``."""
    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        raise InvalidTokenError("missing sub")
    try:
        return UUID(sub)
    except ValueError as exc:
        raise InvalidTokenError("invalid sub") from exc


__all__ = [
    "InvalidTokenError",
    "create_access_token",
    "decode_access_token",
    "parse_user_id_from_payload",
]
