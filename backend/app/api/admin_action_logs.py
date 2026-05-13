"""Admin-only action log listing (Step 20)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.core.auth_dependencies import CurrentUserContext, require_admin_user
from app.services.action_log_service import list_action_logs, write_action_log_safe

router = APIRouter(prefix="/api/admin/action-logs", tags=["admin-action-logs"])


@router.get("", response_model=None)
def admin_list_action_logs(
    request: Request,
    admin: CurrentUserContext = Depends(require_admin_user),
    user_id: Annotated[uuid.UUID | None, Query()] = None,
    action_type: Annotated[str | None, Query()] = None,
    result: Annotated[str | None, Query()] = None,
    data_source_id: Annotated[uuid.UUID | None, Query()] = None,
    target_file_id: Annotated[uuid.UUID | None, Query()] = None,
    keyword: Annotated[str | None, Query()] = None,
    from_date: Annotated[str | None, Query()] = None,
    to_date: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    try:
        total, items = list_action_logs(
            user_id=user_id,
            action_type=action_type,
            result=result,
            data_source_id=data_source_id,
            target_file_id=target_file_id,
            keyword=keyword,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:  # pragma: no cover
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to list action logs",
                "error": str(exc),
            },
        )

    write_action_log_safe(
        user_id=admin.id,
        action_type="ACTION_LOG_VIEW",
        result="SUCCESS",
        request=request,
        detail={
            "filters": {
                "user_id": str(user_id) if user_id else None,
                "action_type": action_type,
                "result": result,
                "keyword_set": bool((keyword or "").strip()),
                "from_date": from_date,
                "to_date": to_date,
            },
            "limit": limit,
            "offset": offset,
            "returned": len(items),
        },
    )

    return JSONResponse(
        status_code=200,
        content={"status": "ok", "total": total, "items": items},
    )


__all__ = ["router"]
