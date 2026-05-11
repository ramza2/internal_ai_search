"""REST API for WebDAV / local data source registrations (admin-style CRUD).

Stores credentials encrypted; probes WebDAV via PROPFIND (Depth: 0) and lists
root children via Depth: 1 preview — no recursion, downloads, indexing, or
`files` table writes from listing.
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
