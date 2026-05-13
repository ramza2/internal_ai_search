"""Read-only file metadata API (statistics, previews & dashboards).

Statistics routes aggregate the ``files`` table only. Preview routes
(Step 18) read ``file_contents.extracted_text`` plus optional
``document_chunks`` metadata — they never download from WebDAV, never
mutate files, and never return credentials.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.core.auth_dependencies import CurrentUserContext, require_admin_user, require_password_ready_user
from app.schemas.file_preview import (
    CONTEXT_LINES_DEFAULT,
    MAX_CHARS_DEFAULT,
)
from app.services.action_log_service import write_action_log_safe
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


def _log_file_preview(
    *,
    request: Request,
    user_id,
    file_id: UUID,
    chunk_id: UUID | None,
    start_line: int | None,
    end_line: int | None,
    context_lines: int,
    max_chars: int,
    result: str,
    remote_path: str | None,
    error_message: str | None,
) -> None:
    write_action_log_safe(
        user_id=user_id,
        action_type="FILE_PREVIEW",
        result=result,
        request=request,
        target_file_id=file_id,
        target_file_path=remote_path,
        detail={
            "chunk_id": str(chunk_id) if chunk_id else None,
            "start_line": start_line,
            "end_line": end_line,
            "context_lines": context_lines,
            "max_chars": max_chars,
        },
        error_message=error_message,
    )


@router.get("/stats", response_model=None)
def get_files_stats(
    _: CurrentUserContext = Depends(require_admin_user),
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
    except DataSourceNotFound:
        return _not_found_resp()
    except Exception as exc:  # pragma: no cover - defensive
        return _stats_error_resp(exc)
    return JSONResponse(status_code=200, content=payload)


@router.get("/{file_id}/preview", response_model=None)
def get_file_preview(
    request: Request,
    file_id: UUID,
    user: CurrentUserContext = Depends(require_password_ready_user),
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
        _log_file_preview(
            request=request,
            user_id=user.id,
            file_id=file_id,
            chunk_id=chunk_id,
            start_line=start_line,
            end_line=end_line,
            context_lines=context_lines,
            max_chars=max_chars,
            result="FAIL",
            remote_path=None,
            error_message=exc.message,
        )
        return _preview_error_resp(exc)
    except Exception as exc:  # pragma: no cover - defensive
        _log_file_preview(
            request=request,
            user_id=user.id,
            file_id=file_id,
            chunk_id=chunk_id,
            start_line=start_line,
            end_line=end_line,
            context_lines=context_lines,
            max_chars=max_chars,
            result="FAIL",
            remote_path=None,
            error_message=str(exc),
        )
        return _preview_server_err(exc)
    rpath = payload.file.remote_path if payload.file else None
    _log_file_preview(
        request=request,
        user_id=user.id,
        file_id=file_id,
        chunk_id=chunk_id,
        start_line=start_line,
        end_line=end_line,
        context_lines=context_lines,
        max_chars=max_chars,
        result="SUCCESS",
        remote_path=rpath,
        error_message=None,
    )
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


@router.get("/{file_id}/chunks/{chunk_id}/preview", response_model=None)
def get_chunk_preview(
    request: Request,
    file_id: UUID,
    chunk_id: UUID,
    user: CurrentUserContext = Depends(require_password_ready_user),
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
        _log_file_preview(
            request=request,
            user_id=user.id,
            file_id=file_id,
            chunk_id=chunk_id,
            start_line=None,
            end_line=None,
            context_lines=context_lines,
            max_chars=max_chars,
            result="FAIL",
            remote_path=None,
            error_message=exc.message,
        )
        return _preview_error_resp(exc)
    except Exception as exc:  # pragma: no cover - defensive
        _log_file_preview(
            request=request,
            user_id=user.id,
            file_id=file_id,
            chunk_id=chunk_id,
            start_line=None,
            end_line=None,
            context_lines=context_lines,
            max_chars=max_chars,
            result="FAIL",
            remote_path=None,
            error_message=str(exc),
        )
        return _preview_server_err(exc)
    rpath = payload.file.remote_path if payload.file else None
    _log_file_preview(
        request=request,
        user_id=user.id,
        file_id=file_id,
        chunk_id=chunk_id,
        start_line=None,
        end_line=None,
        context_lines=context_lines,
        max_chars=max_chars,
        result="SUCCESS",
        remote_path=rpath,
        error_message=None,
    )
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))
