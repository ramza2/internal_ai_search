"""Admin-only user management API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.core.auth_dependencies import CurrentUserContext, require_admin_user
from app.schemas.auth import AdminRolePatchRequest, user_jsonable
from app.services.admin_users_service import (
    AdminUsersError,
    activate_user,
    approve_user,
    deactivate_user,
    list_users,
    lock_user,
    set_user_role,
)

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


def _err(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "message": message},
    )


@router.get("", response_model=None)
def admin_list_users(
    _: CurrentUserContext = Depends(require_admin_user),
    status: Annotated[str | None, Query()] = None,
    role: Annotated[str | None, Query()] = None,
    keyword: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    try:
        total, items = list_users(
            status=status,
            role=role,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )
    except AdminUsersError as exc:
        return _err(exc.status_code, exc.message)
    except Exception as exc:  # pragma: no cover
        return _err(500, str(exc))
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "total": total,
            "items": [user_jsonable(i) for i in items],
        },
    )


@router.patch("/{user_id}/approve", response_model=None)
def admin_approve_user(
    user_id: uuid.UUID,
    _: CurrentUserContext = Depends(require_admin_user),
) -> JSONResponse:
    try:
        user = approve_user(user_id)
    except AdminUsersError as exc:
        return _err(exc.status_code, exc.message)
    except Exception as exc:  # pragma: no cover
        return _err(500, str(exc))
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "message": "User approved successfully",
            "user": user_jsonable(user),
        },
    )


@router.patch("/{user_id}/deactivate", response_model=None)
def admin_deactivate_user(
    user_id: uuid.UUID,
    _: CurrentUserContext = Depends(require_admin_user),
) -> JSONResponse:
    try:
        user = deactivate_user(user_id)
    except AdminUsersError as exc:
        return _err(exc.status_code, exc.message)
    except Exception as exc:  # pragma: no cover
        return _err(500, str(exc))
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "message": "User deactivated successfully",
            "user": user_jsonable(user),
        },
    )


@router.patch("/{user_id}/lock", response_model=None)
def admin_lock_user(
    user_id: uuid.UUID,
    _: CurrentUserContext = Depends(require_admin_user),
) -> JSONResponse:
    try:
        user = lock_user(user_id)
    except AdminUsersError as exc:
        return _err(exc.status_code, exc.message)
    except Exception as exc:  # pragma: no cover
        return _err(500, str(exc))
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "message": "User locked successfully",
            "user": user_jsonable(user),
        },
    )


@router.patch("/{user_id}/activate", response_model=None)
def admin_activate_user(
    user_id: uuid.UUID,
    _: CurrentUserContext = Depends(require_admin_user),
) -> JSONResponse:
    try:
        user = activate_user(user_id)
    except AdminUsersError as exc:
        return _err(exc.status_code, exc.message)
    except Exception as exc:  # pragma: no cover
        return _err(500, str(exc))
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "message": "User activated successfully",
            "user": user_jsonable(user),
        },
    )


@router.patch("/{user_id}/role", response_model=None)
def admin_set_role(
    user_id: uuid.UUID,
    body: AdminRolePatchRequest,
    _: CurrentUserContext = Depends(require_admin_user),
) -> JSONResponse:
    try:
        user = set_user_role(user_id, body.role)
    except AdminUsersError as exc:
        return _err(exc.status_code, exc.message)
    except Exception as exc:  # pragma: no cover
        return _err(500, str(exc))
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "message": "User role updated successfully",
            "user": user_jsonable(user),
        },
    )


__all__ = ["router"]
