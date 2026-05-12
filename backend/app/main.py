from fastapi import FastAPI

from app.api.data_sources import router as data_sources_router
from app.api.files import router as files_router
from app.api.health import router as health_router
from app.core.config import settings


app = FastAPI(
    title="Internal AI Search Backend",
    version="0.1.0",
    description="Backend API for internal-ai-search project.",
)

app.include_router(health_router, tags=["health"])
app.include_router(data_sources_router)
app.include_router(files_router)


@app.get("/", tags=["root"])
def root() -> dict[str, str]:
    return {
        "service": settings.service_name,
        "message": "Internal AI Search Backend is running.",
    }
