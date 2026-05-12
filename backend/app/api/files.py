"""Read-only file metadata API (statistics & dashboards).

This module never triggers WebDAV calls, file downloads, body analysis,
chunking, or embedding work — it only aggregates the ``files`` table.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.services.data_source_service import DataSourceNotFound
from app.services.file_stats_service import get_file_statistics


router = APIRouter(prefix="/api/files", tags=["files"])


def _not_found_resp() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"status": "error", "message": "Data source not found"},
    )


def _stats_error_resp(exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Failed to retrieve file statistics",
            "error": str(exc),
        },
    )


@router.get("/stats", response_model=None)
def get_files_stats(
    data_source_id: Annotated[UUID | None, Query()] = None,
    include_deleted: Annotated[bool, Query()] = False,
) -> JSONResponse:
    """Return file statistics for all data sources (default) or a single one.

    When ``data_source_id`` is omitted the response includes a
    ``by_data_source`` breakdown alongside the global totals.
    """
    try:
        payload = get_file_statistics(
            data_source_id=data_source_id,
            include_deleted=include_deleted,
        )
        return JSONResponse(status_code=200, content=payload)
    except DataSourceNotFound:
        return _not_found_resp()
    except Exception as exc:  # pragma: no cover - defensive
        return _stats_error_resp(exc)
