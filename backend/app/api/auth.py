"""Authentication API (signup, login, me, change-password)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.auth_dependencies import CurrentUserContext, get_current_user
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    SignupRequest,
    user_jsonable,
)
from app.services.action_log_service import write_action_log_safe
from app.services.auth_service import AuthServiceError, change_password, login, me_dict, signup

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _auth_err(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "message": message},
    )


@router.post("/signup", response_model=None)
def auth_signup(request: Request, body: SignupRequest) -> JSONResponse:
    try:
        user = signup(
            login_id=body.login_id,
            password=body.password,
            name=body.name,
            email=body.email,
            department=body.department,
        )
    except AuthServiceError as exc:
        write_action_log_safe(
            user_id=None,
            action_type="SIGNUP",
            result="FAIL",
            request=request,
            detail={
                "login_id": body.login_id,
                "email": body.email,
                "department": body.department,
                "status": "PENDING",
            },
            error_message=exc.message,
        )
        return _auth_err(exc.status_code, exc.message)
    except Exception as exc:  # pragma: no cover
        write_action_log_safe(
            user_id=None,
            action_type="SIGNUP",
            result="FAIL",
            request=request,
            detail={
                "login_id": body.login_id,
                "email": body.email,
                "department": body.department,
                "status": "unknown",
            },
            error_message=str(exc),
        )
        return _auth_err(500, str(exc))
    write_action_log_safe(
        user_id=None,
        action_type="SIGNUP",
        result="SUCCESS",
        request=request,
        detail={
            "login_id": user["login_id"],
            "email": user.get("email"),
            "department": user.get("department"),
            "status": user.get("status"),
        },
    )
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "message": "Signup request submitted. Administrator approval is required.",
            "user": user_jsonable(user),
        },
    )


@router.post("/login", response_model=None)
def auth_login(request: Request, body: LoginRequest) -> JSONResponse:
    try:
        data = login(login_id=body.login_id, password=body.password)
    except AuthServiceError as exc:
        write_action_log_safe(
            user_id=None,
            action_type="LOGIN_FAILED",
            result="FAIL",
            request=request,
            detail={"login_id": (body.login_id or "").strip()},
            error_message=exc.message,
        )
        return _auth_err(exc.status_code, exc.message)
    except Exception as exc:  # pragma: no cover
        write_action_log_safe(
            user_id=None,
            action_type="LOGIN_FAILED",
            result="FAIL",
            request=request,
            detail={"login_id": (body.login_id or "").strip()},
            error_message=str(exc),
        )
        return _auth_err(500, str(exc))
    uid = uuid.UUID(data["user"]["id"])
    write_action_log_safe(
        user_id=uid,
        action_type="LOGIN",
        result="SUCCESS",
        request=request,
        detail={
            "login_id": data["user"].get("login_id"),
            "role": data["user"].get("role"),
            "status": data["user"].get("status"),
        },
    )
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "access_token": data["access_token"],
            "token_type": data["token_type"],
            "expires_in_minutes": data["expires_in_minutes"],
            "user": user_jsonable(data["user"]),
        },
    )


@router.get("/me", response_model=None)
def auth_me(user: CurrentUserContext = Depends(get_current_user)) -> JSONResponse:
    try:
        payload = me_dict(user_id=user.id)
    except AuthServiceError as exc:
        return _auth_err(exc.status_code, exc.message)
    except Exception as exc:  # pragma: no cover
        return _auth_err(500, str(exc))
    return JSONResponse(
        status_code=200,
        content={"status": "ok", "user": user_jsonable(payload)},
    )


@router.post("/change-password", response_model=None)
def auth_change_password(
    request: Request,
    body: ChangePasswordRequest,
    user: CurrentUserContext = Depends(get_current_user),
) -> JSONResponse:
    try:
        change_password(
            user_id=user.id,
            current_password=body.current_password,
            new_password=body.new_password,
        )
    except AuthServiceError as exc:
        write_action_log_safe(
            user_id=user.id,
            action_type="PASSWORD_CHANGE",
            result="FAIL",
            request=request,
            detail={},
            error_message=exc.message,
        )
        return _auth_err(exc.status_code, exc.message)
    except Exception as exc:  # pragma: no cover
        write_action_log_safe(
            user_id=user.id,
            action_type="PASSWORD_CHANGE",
            result="FAIL",
            request=request,
            detail={},
            error_message=str(exc),
        )
        return _auth_err(500, str(exc))
    write_action_log_safe(
        user_id=user.id,
        action_type="PASSWORD_CHANGE",
        result="SUCCESS",
        request=request,
        detail={},
    )
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "message": "Password changed successfully",
        },
    )


__all__ = ["router"]
