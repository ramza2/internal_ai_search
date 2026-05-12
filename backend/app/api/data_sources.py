"""REST API for WebDAV / local data source registrations (admin-style CRUD).

Stores credentials encrypted; probes WebDAV via PROPFIND (Depth: 0),
previews root children via Depth: 1 (no DB writes), upserts root children
into the ``files`` table via a one-level sync, walks the tree with a
bounded BFS recursive sync (PROPFIND Depth: 1 per folder, ``max_depth`` /
``max_items``-limited) with opt-in soft-mark deletion detection
(``detect_deleted``), downloads PENDING text files into ``file_contents``
via the Step-12 processor, slices the resulting ``extracted_text`` into
``document_chunks`` via the Step-13 chunker, and embeds those chunks into
``document_chunks.embedding vector(1024)`` via the Step-14 embedder
(bumping ``files.last_indexed_at`` once every chunk of that file has a
non-``NULL`` vector). No retrieval / RAG / search at this stage.
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
from app.services.chunk_embedding_service import (
    FileNotInDataSource,
    run_embed_pending_chunks,
)
from app.services.chunk_text_processor_service import (
    InvalidChunkParameters,
    run_chunk_completed_text,
)
from app.services.file_recursive_sync_service import run_webdav_recursive_sync
from app.services.file_stats_service import get_file_statistics
from app.services.file_sync_service import run_webdav_root_sync
from app.services.pending_text_processor_service import (
    run_process_pending_text,
)
from app.services.text_extraction_service import parse_include_extensions
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


@router.post("/{data_source_id}/process-pending-text", response_model=None)
def process_data_source_pending_text(
    data_source_id: UUID,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    max_file_size_bytes: Annotated[int, Query(ge=1, le=268_435_456)] = 5_242_880,
    include_extensions: Annotated[str | None, Query()] = None,
    dry_run: Annotated[bool, Query()] = False,
) -> JSONResponse:
    """Download PENDING text files and persist their text in ``file_contents``.

    Walks the configured WebDAV source via HTTP GET (no PROPFIND), keeps
    each file's transaction tiny so a single bad file cannot poison the
    batch, and never logs Authorization headers or credential plaintext.

    Out of scope at this milestone: chunking, embeddings,
    ``document_chunks`` writes, PDF/DOCX/HWP/XLSX parsing, and any RAG
    / search behavior.
    """
    try:
        ext_set = parse_include_extensions(include_extensions)
        payload, code = run_process_pending_text(
            settings,
            data_source_id,
            limit=limit,
            max_file_size_bytes=max_file_size_bytes,
            include_extensions=ext_set,
            dry_run=dry_run,
        )
        return JSONResponse(status_code=code, content=payload)
    except datasource_svc.DataSourceNotFound:
        return _not_found_resp()
    except Exception as exc:  # pragma: no cover
        return _srv_err_resp(exc)


@router.post("/{data_source_id}/chunk-completed-text", response_model=None)
def chunk_data_source_completed_text(
    data_source_id: UUID,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    chunk_size: Annotated[int, Query(ge=200, le=10_000)] = 1200,
    chunk_overlap: Annotated[int, Query(ge=0, le=9_999)] = 200,
    min_chunk_size: Annotated[int, Query(ge=0, le=10_000)] = 100,
    reprocess: Annotated[bool, Query()] = False,
    dry_run: Annotated[bool, Query()] = False,
    include_extensions: Annotated[str | None, Query()] = None,
) -> JSONResponse:
    """Slice ``file_contents.extracted_text`` into ``document_chunks``.

    Character-based splitter with paragraph-boundary preference. Walks
    files whose ``analysis_status='COMPLETED'`` and that have a
    populated ``file_contents`` row. Per-file transactions keep one bad
    file from poisoning the batch; ``files.last_indexed_at`` is **not**
    updated here because embeddings still need to be generated in a
    later milestone (``document_chunks.embedding`` is written as
    ``NULL`` for now).
    """
    try:
        ext_set = parse_include_extensions(include_extensions)
        payload, code = run_chunk_completed_text(
            data_source_id,
            limit=limit,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            min_chunk_size=min_chunk_size,
            reprocess=reprocess,
            dry_run=dry_run,
            include_extensions=ext_set,
        )
        return JSONResponse(status_code=code, content=payload)
    except datasource_svc.DataSourceNotFound:
        return _not_found_resp()
    except InvalidChunkParameters as exc:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Invalid chunking parameters",
                "error": exc.error,
            },
        )
    except Exception as exc:  # pragma: no cover
        return _srv_err_resp(exc)


@router.post("/{data_source_id}/embed-pending-chunks", response_model=None)
def embed_data_source_pending_chunks(
    data_source_id: UUID,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    batch_size: Annotated[int, Query(ge=1, le=128)] = 32,
    include_extensions: Annotated[str | None, Query()] = None,
    reembed: Annotated[bool, Query()] = False,
    file_id: Annotated[UUID | None, Query()] = None,
    dry_run: Annotated[bool, Query()] = False,
) -> JSONResponse:
    """Embed ``document_chunks`` with ``embedding IS NULL`` and store
    1024-D vectors into ``document_chunks.embedding vector(1024)``.

    Reuses the Step-3 Ollama embedding client (``bge-m3``, dimension
    1024). Per-batch transactions keep one bad chunk from poisoning
    the whole job; ``files.last_indexed_at`` is bumped only after
    every chunk of that file carries a non-``NULL`` embedding. With
    ``reembed=true`` existing embeddings are regenerated. ``file_id``
    narrows the batch to a single file (the file must belong to the
    URL data source — otherwise 404). ``dry_run=true`` returns the
    target / batch counts and per-file ``target_chunks`` without
    touching the database or calling the embedding API.

    Out of scope at this milestone: search APIs, RAG retrieval / answer
    generation, chat, PDF / DOCX / HWP / XLSX parsing.
    """
    try:
        ext_set = parse_include_extensions(include_extensions)
        payload, code = run_embed_pending_chunks(
            settings,
            data_source_id,
            limit=limit,
            batch_size=batch_size,
            include_extensions=ext_set,
            reembed=reembed,
            file_id=file_id,
            dry_run=dry_run,
        )
        return JSONResponse(status_code=code, content=payload)
    except datasource_svc.DataSourceNotFound:
        return _not_found_resp()
    except FileNotInDataSource:
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "message": "File not found in data source",
            },
        )
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
