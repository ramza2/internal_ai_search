"""Bcrypt password hashing (Step 19 auth).

Plaintext passwords never touch the database — only ``hash_password``
output is stored in ``app_users.password_hash``.
"""

from __future__ import annotations

import bcrypt


def hash_password(plain_password: str) -> str:
    """Return a bcrypt ASCII string suitable for ``app_users.password_hash``."""
    pw = plain_password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pw, salt).decode("ascii")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Constant-time verification against a stored bcrypt hash."""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("ascii"),
        )
    except ValueError:
        return False


__all__ = ["hash_password", "verify_password"]
