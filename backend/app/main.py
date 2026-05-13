from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.admin_action_logs import router as admin_action_logs_router
from app.api.admin_dashboard import router as admin_dashboard_router
from app.api.admin_users import router as admin_users_router
from app.api.answer import router as answer_router
from app.api.auth import router as auth_router
from app.api.data_sources import router as data_sources_router
from app.api.files import router as files_router
from app.api.health import router as health_router
from app.api.search import router as search_router
from app.core.config import settings
from app.services.auth_bootstrap_service import ensure_initial_admin


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Runs startup hooks (initial admin bootstrap) before serving traffic."""
    ensure_initial_admin()
    yield


app = FastAPI(
    title="Internal AI Search Backend",
    version="0.1.0",
    description="Backend API for internal-ai-search project.",
    lifespan=lifespan,
)


@app.exception_handler(HTTPException)
async def _http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    """Return flat ``{status, message}`` bodies for dependency auth errors."""
    detail = exc.detail
    if isinstance(detail, dict) and detail.get("status") == "error":
        return JSONResponse(status_code=exc.status_code, content=detail)
    if isinstance(detail, str):
        return JSONResponse(
            status_code=exc.status_code,
            content={"status": "error", "message": detail},
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": str(detail)},
    )


app.include_router(health_router, tags=["health"])
app.include_router(admin_action_logs_router)
app.include_router(admin_dashboard_router)
app.include_router(auth_router)
app.include_router(admin_users_router)
app.include_router(data_sources_router)
app.include_router(files_router)
app.include_router(search_router)
app.include_router(answer_router)


@app.get("/", tags=["root"])
def root() -> dict[str, str]:
    return {
        "service": settings.service_name,
        "message": "Internal AI Search Backend is running.",
    }
