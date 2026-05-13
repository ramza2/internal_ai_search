"""Admin dashboard summary (read-only aggregates)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.auth_dependencies import CurrentUserContext, require_admin_user
from app.services.admin_dashboard_service import DashboardSummaryError, fetch_dashboard_summary

router = APIRouter(prefix="/api/admin/dashboard", tags=["admin-dashboard"])


@router.get("/summary", response_model=None)
def admin_dashboard_summary(
    _: CurrentUserContext = Depends(require_admin_user),
) -> JSONResponse:
    """Operational snapshot for the admin home screen.

    Not written to ``action_logs`` — frequent UI polling.
    """
    try:
        envelope = fetch_dashboard_summary()
    except DashboardSummaryError as exc:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to retrieve dashboard summary",
                "error": exc.message,
            },
        )
    except Exception as exc:  # pragma: no cover - defensive
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to retrieve dashboard summary",
                "error": str(exc),
            },
        )
    return JSONResponse(
        status_code=200,
        content=envelope.model_dump(mode="json"),
    )
