"""Request / response models for Step 19 auth APIs."""

from __future__ import annotations

import re
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_LOGIN_ID_RE = re.compile(r"^[a-zA-Z0-9_]{3,64}$")


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    login_id: Annotated[str, Field(min_length=3, max_length=64)]
    password: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    email: Annotated[str, Field(min_length=3, max_length=254)]
    department: Annotated[str | None, Field(default=None, max_length=200)] = None

    @field_validator("login_id")
    @classmethod
    def _login_id_chars(cls, v: str) -> str:
        s = v.strip()
        if not _LOGIN_ID_RE.match(s):
            raise ValueError(
                "login_id must be 3–64 characters: letters, digits, underscore only"
            )
        return s


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    login_id: Annotated[str, Field(min_length=1)]
    password: Annotated[str, Field(min_length=1)]


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    current_password: Annotated[str, Field(min_length=1)]
    new_password: Annotated[str, Field(min_length=1)]


class AdminRolePatchRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: Annotated[str, Field(min_length=1)]

    @field_validator("role")
    @classmethod
    def _role_upper(cls, v: str) -> str:
        s = v.strip().upper()
        if s not in ("USER", "ADMIN"):
            raise ValueError("role must be USER or ADMIN")
        return s


def user_jsonable(u: dict[str, Any]) -> dict[str, Any]:
    """Drop any stray secret keys before sending to the client."""
    blocked = frozenset({"password_hash", "credential_secret", "credential_secret_enc"})
    return {k: v for k, v in u.items() if k not in blocked}


__all__ = [
    "AdminRolePatchRequest",
    "ChangePasswordRequest",
    "LoginRequest",
    "SignupRequest",
    "user_jsonable",
]
