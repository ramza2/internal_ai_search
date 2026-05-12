"""REST API for WebDAV / local data source registrations (admin-style CRUD).

Stores credentials encrypted; probes WebDAV via PROPFIND (Depth: 0),
previews root children via Depth: 1 (no DB writes), upserts root children
into the ``files`` table via a one-level sync, and walks the tree with a
bounded BFS recursive sync (PROPFIND Depth: 1 per folder, ``max_depth`` /
``max_items``-limited). No downloads, hashing, chunking, embedding, or
deletion detection at this stage.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.schemas.data_source import (
    DataSourceCreate,
    DataSourceListEnvelope,
    DataSourceResponse,
    DataSourceUpdate,
    SourceType,
)
from app.services.data_source_service import (
    DataSourceBadRequest,
    DataSourceConflict,
    DataSourceNotFound,
)
from app.services import data_source_service as datasource_svc
from app.services.file_recursive_sync_service import run_webdav_recursive_sync
from app.services.file_stats_service import get_file_statistics
from app.services.file_sync_service import run_webdav_root_sync
from app.webdav.connection_test import run_webdav_connection_test
from app.webdav.listing import run_webdav_root_listing


router = APIRouter(prefix="/api/data-sources", tags=["data-sources"])


def _not_found_resp() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"status": "error", "message": "Data source not found"},
    )


def _conflict_resp(exc: Exception) -> JSONResponse:
    detail = str(exc).strip() or None
    return JSONResponse(
        status_code=409,
        content={
            "status": "error",
            "message": "Data source name already exists",
            **({"error": detail} if detail else {}),
        },
    )


def _bad_req_resp(msg: str, err: str | None = None) -> JSONResponse:
    body = {"status": "error", "message": msg}
    if err:
        body["error"] = err
    return JSONResponse(status_code=400, content=body)


def _srv_err_resp(exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal server error",
            "error": str(exc),
        },
    )


@router.get("", response_model=None)
def list_data_sources(
    include_inactive: Annotated[bool, Query()] = False,
    source_type: Annotated[SourceType | None, Query(description="OWNCLOUD, …")] = None,
    keyword: Annotated[str | None, Query()] = None,
) -> DataSourceListEnvelope | JSONResponse:
    try:
        st_str = source_type.value if source_type else None
        raw = datasource_svc.list_data_sources(
            include_inactive=include_inactive,
            source_type=st_str,
            keyword=keyword,
        )
        return DataSourceListEnvelope.model_validate(raw)
    except Exception as exc:  # pragma: no cover - defensive
        return _srv_err_resp(exc)


@router.post("/{data_source_id}/test-connection", response_model=None)
def test_data_source_webdav_connection(data_source_id: UUID) -> JSONResponse:
    try:
        payload, code = run_webdav_connection_test(settings, data_source_id)
        return JSONResponse(status_code=code, content=payload)
    except datasource_svc.DataSourceNotFound:
        return _not_found_resp()
    except Exception as exc:  # pragma: no cover
        return _srv_err_resp(exc)


@router.post("/{data_source_id}/list-root", response_model=None)
def list_data_source_webdav_root(
    data_source_id: UUID,
    limit: Annotated[int, Query(ge=1, le=5000)] = 200,
    include_hidden: Annotated[bool, Query()] = False,
) -> JSONResponse:
    """List immediate children of the registered WebDAV root (PROPFIND Depth: 1).

    Does not persist file metadata; optionally updates ``last_connection_*`` only.
    """
    try:
        payload, code = run_webdav_root_listing(
            settings,
            data_source_id,
            limit=limit,
            include_hidden=include_hidden,
        )
        return JSONResponse(status_code=code, content=payload)
    except datasource_svc.DataSourceNotFound:
        return _not_found_resp()
    except Exception as exc:  # pragma: no cover
        return _srv_err_resp(exc)


@router.get("/{data_source_id}/file-stats", response_model=None)
def get_data_source_file_stats(
    data_source_id: UUID,
    include_deleted: Annotated[bool, Query()] = False,
) -> JSONResponse:
    """Convenience alias for ``GET /api/files/stats?data_source_id={id}``."""
    try:
        payload = get_file_statistics(
            data_source_id=data_source_id,
            include_deleted=include_deleted,
        )
        return JSONResponse(status_code=200, content=payload)
    except DataSourceNotFound:
        return _not_found_resp()
    except Exception as exc:  # pragma: no cover - defensive
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to retrieve file statistics",
                "error": str(exc),
            },
        )


@router.post("/{data_source_id}/sync-root", response_model=None)
def sync_data_source_webdav_root(
    data_source_id: UUID,
    limit: Annotated[int, Query(ge=1, le=10000)] = 1000,
    include_hidden: Annotated[bool, Query()] = False,
) -> JSONResponse:
    """Upsert direct children of the registered WebDAV root into ``files``.

    Single transaction: all-or-nothing across the upserts and the
    ``data_sources.last_scan_at`` update. No recursion, downloads, hashing,
    chunking, or deletion detection — only one level beneath ``webdav_root_path``.
    """
    try:
        payload, code = run_webdav_root_sync(
            settings,
            data_source_id,
            limit=limit,
            include_hidden=include_hidden,
        )
        return JSONResponse(status_code=code, content=payload)
    except datasource_svc.DataSourceNotFound:
        return _not_found_resp()
    except Exception as exc:  # pragma: no cover
        return _srv_err_resp(exc)


@router.post("/{data_source_id}/sync-tree", response_model=None)
def sync_data_source_webdav_tree(
    data_source_id: UUID,
    start_path: Annotated[str, Query()] = "/",
    max_depth: Annotated[int, Query(ge=0, le=20)] = 3,
    max_items: Annotated[int, Query(ge=1, le=50000)] = 5000,
    include_hidden: Annotated[bool, Query()] = False,
    apply_exclusions: Annotated[bool, Query()] = True,
    detect_deleted: Annotated[bool, Query()] = False,
) -> JSONResponse:
    """Bounded BFS recursive WebDAV sync (PROPFIND Depth: 1 per folder).

    Upserts every visited file/folder into ``files`` in a single
    transaction. ``max_depth`` and ``max_items`` bound the walk; the
    operation runs synchronously inside the request and is expected to
    move to a worker queue in later milestones.

    ``detect_deleted`` (default ``false``) opts into Step 11's soft-mark of
    rows that disappeared between scans. Detection only runs when the walk
    was complete and unfiltered (``truncated=false``, ``failed_count=0``,
    ``apply_exclusions=false``, ``include_hidden=true``); otherwise a
    skip-reason warning is returned and ``deleted_marked_count`` stays 0.
    """
    try:
        payload, code = run_webdav_recursive_sync(
            settings,
            data_source_id,
            start_path=start_path,
            max_depth=max_depth,
            max_items=max_items,
            include_hidden=include_hidden,
            apply_exclusions=apply_exclusions,
            detect_deleted=detect_deleted,
        )
        return JSONResponse(status_code=code, content=payload)
    except datasource_svc.DataSourceNotFound:
        return _not_found_resp()
    except Exception as exc:  # pragma: no cover
        return _srv_err_resp(exc)


@router.get("/{data_source_id}", response_model=None)
def get_data_source(data_source_id: UUID) -> DataSourceResponse | JSONResponse:
    try:
        payload = datasource_svc.get_data_source(ds_id=data_source_id)
        return DataSourceResponse.model_validate(payload)
    except DataSourceNotFound:
        return _not_found_resp()
    except Exception as exc:  # pragma: no cover
        return _srv_err_resp(exc)


@router.post("", status_code=201, response_model=None)
def create_data_source(body: DataSourceCreate) -> DataSourceResponse | JSONResponse:
    try:
        payload = datasource_svc.create_data_source(settings=settings, body=body)
        return DataSourceResponse.model_validate(payload)
    except DataSourceConflict as exc:
        return _conflict_resp(exc)
    except DataSourceBadRequest as exc:
        return _bad_req_resp(exc.message, exc.error)
    except Exception as exc:  # pragma: no cover
        return _srv_err_resp(exc)


@router.put("/{data_source_id}", response_model=None)
def update_data_source(
    data_source_id: UUID,
    body: DataSourceUpdate,
) -> DataSourceResponse | JSONResponse:
    try:
        payload = datasource_svc.update_data_source(
            settings=settings, ds_id=data_source_id, body=body
        )
        return DataSourceResponse.model_validate(payload)
    except DataSourceNotFound:
        return _not_found_resp()
    except DataSourceConflict as exc:
        return _conflict_resp(exc)
    except DataSourceBadRequest as exc:
        return _bad_req_resp(exc.message, exc.error)
    except Exception as exc:  # pragma: no cover
        return _srv_err_resp(exc)


@router.patch("/{data_source_id}/deactivate", response_model=None)
def deactivate_data_source(data_source_id: UUID) -> DataSourceResponse | JSONResponse:
    try:
        payload = datasource_svc.set_active(ds_id=data_source_id, is_active=False)
        return DataSourceResponse.model_validate(payload)
    except DataSourceNotFound:
        return _not_found_resp()
    except Exception as exc:  # pragma: no cover
        return _srv_err_resp(exc)


@router.patch("/{data_source_id}/activate", response_model=None)
def activate_data_source(data_source_id: UUID) -> DataSourceResponse | JSONResponse:
    try:
        payload = datasource_svc.set_active(ds_id=data_source_id, is_active=True)
        return DataSourceResponse.model_validate(payload)
    except DataSourceNotFound:
        return _not_found_resp()
    except Exception as exc:  # pragma: no cover
        return _srv_err_resp(exc)
