"""REST API for the Step-15 vector search endpoint.

One POST route: ``POST /api/search``. Request body is validated by
:class:`SearchRequest`, the orchestrator
(:func:`run_search`) handles embedding + pgvector cosine search, and
the response is rendered with :class:`SearchResponse`.

This module deliberately keeps the JSON error shapes consistent with
the rest of the project:

- ``query`` empty / missing → ``400 Search query is required``
- ``data_source_id`` missing or inactive → ``404 Data source not found``
- query embedding failure → ``502 Failed to generate embedding``
- DB search failure → ``500 Search query failed``

No retrieval / RAG / answer generation / chat is wired here.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.search import SearchRequest, SearchResponse
from app.services.search_service import (
    DataSourceNotFound,
    EmbeddingFailure,
    SearchDatabaseError,
    run_search,
)


router = APIRouter(prefix="/api", tags=["search"])


def _query_required_resp() -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "status": "error",
            "message": "Search query is required",
        },
    )


def _data_source_not_found_resp() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "status": "error",
            "message": "Data source not found",
        },
    )


def _embedding_failure_resp(exc: EmbeddingFailure) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "status": "error",
            "message": "Failed to generate embedding for query",
            "error": exc.message,
            **(
                {"dimension_mismatch": True}
                if exc.dimension_mismatch
                else {}
            ),
        },
    )


def _db_failure_resp(exc: SearchDatabaseError) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Search query failed",
            "error": str(exc),
        },
    )


def _generic_err_resp(exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal server error",
            "error": str(exc),
        },
    )


def _looks_like_empty_query(err: ValidationError | RequestValidationError) -> bool:
    """True when a validation error is caused by an empty/missing ``query``.

    The Pydantic v2 ``errors()`` payload is consulted directly so we
    can convert that one specific failure into the spec's
    ``400 Search query is required`` envelope while every other
    schema violation continues to look like a normal ``422``.
    """
    try:
        details = err.errors()
    except Exception:
        return False
    for d in details:
        loc = d.get("loc") or ()
        if "query" in loc:
            msg = (d.get("msg") or "").lower()
            if (
                "search query is required" in msg
                or "string should have at least" in msg
                or "field required" in msg
            ):
                return True
    return False


@router.post("/search", response_model=None)
async def search_endpoint(request: Request) -> JSONResponse:
    """Resolve a free-text query against ``document_chunks.embedding``.

    Routes don't take a Pydantic body directly because the project's
    spec wants ``query=""`` to surface as **400** (not the default
    ``422``). Reading the JSON manually + validating via
    ``SearchRequest.model_validate`` keeps that mapping isolated.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Request body must be valid JSON",
            },
        )

    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Request body must be a JSON object",
            },
        )

    try:
        parsed = SearchRequest.model_validate(body)
    except ValidationError as exc:
        if _looks_like_empty_query(exc):
            return _query_required_resp()
        return JSONResponse(
            status_code=422,
            content={
                "status": "error",
                "message": "Invalid request body",
                "errors": exc.errors(),
            },
        )

    try:
        response: SearchResponse = run_search(settings, parsed)
    except DataSourceNotFound:
        return _data_source_not_found_resp()
    except EmbeddingFailure as exc:
        return _embedding_failure_resp(exc)
    except SearchDatabaseError as exc:
        return _db_failure_resp(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return _generic_err_resp(exc)

    return JSONResponse(
        status_code=200,
        content=response.model_dump(mode="json"),
    )
