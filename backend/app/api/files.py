"""Read-only file metadata API (statistics, previews & dashboards).

Statistics routes aggregate the ``files`` table only. Preview routes
(Step 18) read ``file_contents.extracted_text`` plus optional
``document_chunks`` metadata — they never download from WebDAV, never
mutate files, and never return credentials.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.schemas.file_preview import (
    CONTEXT_LINES_DEFAULT,
    MAX_CHARS_DEFAULT,
)
from app.services.data_source_service import DataSourceNotFound
from app.services.file_preview_service import PreviewError, run_chunk_preview, run_file_preview
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


def _preview_error_resp(exc: PreviewError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": exc.message},
    )


def _preview_server_err(exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal server error",
            "error": str(exc),
        },
    )


@router.get("/{file_id}/preview", response_model=None)
def get_file_preview(
    file_id: UUID,
    chunk_id: Annotated[UUID | None, Query()] = None,
    start_line: Annotated[int | None, Query()] = None,
    end_line: Annotated[int | None, Query()] = None,
    context_lines: Annotated[int, Query(ge=0, le=200)] = CONTEXT_LINES_DEFAULT,
    max_chars: Annotated[int, Query(ge=1000, le=100_000)] = MAX_CHARS_DEFAULT,
    query: Annotated[str | None, Query()] = None,
    include_full_text: Annotated[bool, Query()] = False,
) -> JSONResponse:
    """Return a bounded line-numbered slice of ``file_contents.extracted_text``.

    Optional ``chunk_id`` centers the window on a stored chunk; optional
    ``start_line`` / ``end_line`` select a line range. ``query`` adds
    character-offset highlight hints (no HTML). ``include_full_text``
    still obeys ``max_chars``.
    """
    q = (query or "").strip() or None
    try:
        payload = run_file_preview(
            file_id=file_id,
            chunk_id=chunk_id,
            start_line=start_line,
            end_line=end_line,
            context_lines=context_lines,
            max_chars=max_chars,
            query=q,
            include_full_text=include_full_text,
        )
    except PreviewError as exc:
        return _preview_error_resp(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return _preview_server_err(exc)
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


@router.get("/{file_id}/chunks/{chunk_id}/preview", response_model=None)
def get_chunk_preview(
    file_id: UUID,
    chunk_id: UUID,
    context_lines: Annotated[int, Query(ge=0, le=200)] = CONTEXT_LINES_DEFAULT,
    max_chars: Annotated[int, Query(ge=1000, le=100_000)] = MAX_CHARS_DEFAULT,
    query: Annotated[str | None, Query()] = None,
) -> JSONResponse:
    """Same body as ``GET /api/files/{file_id}/preview?chunk_id=…``."""
    q = (query or "").strip() or None
    try:
        payload = run_chunk_preview(
            file_id=file_id,
            chunk_id=chunk_id,
            context_lines=context_lines,
            max_chars=max_chars,
            query=q,
        )
    except PreviewError as exc:
        return _preview_error_resp(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return _preview_server_err(exc)
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))
