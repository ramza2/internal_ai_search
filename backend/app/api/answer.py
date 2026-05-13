"""REST API for the Step-16 RAG answer endpoint.

One POST route: ``POST /api/answer``. Reuses the Step-15 search
pipeline for retrieval and the Step-2 Ollama client for generation —
no chat session state, no conversation history, no streaming responses.

Error mapping follows the rest of the project:

- ``query`` empty / missing → ``400 Search query is required``
- ``data_source_id`` missing or inactive → ``404 Data source not found``
- query-embedding failure → ``502 Failed to generate embedding``
- DB search failure → ``500 Search query failed``
- Ollama generate failure / parse failure → ``502 LLM call failed``
- context build defensive failure → ``500 Failed to build RAG context``
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.auth_dependencies import CurrentUserContext, require_password_ready_user
from app.core.config import settings
from app.schemas.answer import AnswerRequest, AnswerResponse
from app.services.action_log_service import write_action_log_safe
from app.services.rag_answer_service import (
    ContextBuildError,
    DataSourceNotFound,
    EmbeddingFailure,
    LLMFailure,
    SearchDatabaseError,
    run_answer,
)


router = APIRouter(prefix="/api", tags=["answer"])


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


def _llm_failure_resp(exc: LLMFailure) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "status": "error",
            "message": "LLM call failed",
            "error": exc.message,
            **({"parse_failed": True} if exc.parse_failed else {}),
        },
    )


def _context_build_resp(exc: ContextBuildError) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Failed to build RAG context",
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


def _looks_like_empty_query(err: ValidationError) -> bool:
    """``True`` when a validation error stems from an empty/missing ``query``.

    Mirrors :func:`app.api.search._looks_like_empty_query` so both
    endpoints produce identical 400 envelopes for the same input
    mistake.
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


def _log_rag(
    *,
    request: Request,
    user_id,
    parsed: AnswerRequest | None,
    result: str,
    response: AnswerResponse | None,
    error_message: str | None,
) -> None:
    q = parsed.query if parsed else None
    detail: dict = {}
    if parsed and response:
        se = response.search
        detail = {
            "search_mode": response.search_mode.value,
            "data_source_id": str(parsed.data_source_id)
            if parsed.data_source_id
            else None,
            "search_limit": parsed.search_limit,
            "context_limit": parsed.context_limit,
            "used_context_count": se.used_context_count,
            "total_results": se.total_results,
            "finish_reason": response.finish_reason,
            "dry_run": parsed.dry_run,
        }
    elif parsed:
        detail = {
            "search_mode": parsed.search_mode.value,
            "data_source_id": str(parsed.data_source_id)
            if parsed.data_source_id
            else None,
            "search_limit": parsed.search_limit,
            "context_limit": parsed.context_limit,
            "used_context_count": None,
            "total_results": None,
            "finish_reason": None,
            "dry_run": parsed.dry_run,
        }
    write_action_log_safe(
        user_id=user_id,
        action_type="RAG_QUESTION",
        result=result,
        request=request,
        search_query=q,
        data_source_id=parsed.data_source_id if parsed else None,
        detail=detail,
        error_message=error_message,
    )


@router.post("/answer", response_model=None)
async def answer_endpoint(
    request: Request,
    user: CurrentUserContext = Depends(require_password_ready_user),
) -> JSONResponse:
    """Run RAG answer generation against the indexed corpus.

    Body is parsed manually so an empty ``query`` surfaces as ``400``
    (the spec's mapping) rather than the default Pydantic ``422``.
    """
    try:
        body = await request.json()
    except Exception:
        _log_rag(
            request=request,
            user_id=user.id,
            parsed=None,
            result="FAIL",
            response=None,
            error_message="Invalid JSON body",
        )
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Request body must be valid JSON",
            },
        )

    if not isinstance(body, dict):
        _log_rag(
            request=request,
            user_id=user.id,
            parsed=None,
            result="FAIL",
            response=None,
            error_message="Body must be a JSON object",
        )
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Request body must be a JSON object",
            },
        )

    try:
        parsed = AnswerRequest.model_validate(body)
    except ValidationError as exc:
        if _looks_like_empty_query(exc):
            _log_rag(
                request=request,
                user_id=user.id,
                parsed=None,
                result="FAIL",
                response=None,
                error_message="Search query is required",
            )
            return _query_required_resp()
        _log_rag(
            request=request,
            user_id=user.id,
            parsed=None,
            result="FAIL",
            response=None,
            error_message="Invalid request body",
        )
        return JSONResponse(
            status_code=422,
            content={
                "status": "error",
                "message": "Invalid request body",
                "errors": exc.errors(),
            },
        )

    try:
        response: AnswerResponse = run_answer(settings, parsed)
    except DataSourceNotFound:
        _log_rag(
            request=request,
            user_id=user.id,
            parsed=parsed,
            result="FAIL",
            response=None,
            error_message="Data source not found",
        )
        return _data_source_not_found_resp()
    except EmbeddingFailure as exc:
        _log_rag(
            request=request,
            user_id=user.id,
            parsed=parsed,
            result="FAIL",
            response=None,
            error_message=exc.message,
        )
        return _embedding_failure_resp(exc)
    except SearchDatabaseError as exc:
        _log_rag(
            request=request,
            user_id=user.id,
            parsed=parsed,
            result="FAIL",
            response=None,
            error_message=str(exc),
        )
        return _db_failure_resp(exc)
    except LLMFailure as exc:
        _log_rag(
            request=request,
            user_id=user.id,
            parsed=parsed,
            result="FAIL",
            response=None,
            error_message=exc.message,
        )
        return _llm_failure_resp(exc)
    except ContextBuildError as exc:
        _log_rag(
            request=request,
            user_id=user.id,
            parsed=parsed,
            result="FAIL",
            response=None,
            error_message=str(exc),
        )
        return _context_build_resp(exc)
    except Exception as exc:  # pragma: no cover - defensive
        _log_rag(
            request=request,
            user_id=user.id,
            parsed=parsed,
            result="FAIL",
            response=None,
            error_message=str(exc),
        )
        return _generic_err_resp(exc)

    _log_rag(
        request=request,
        user_id=user.id,
        parsed=parsed,
        result="SUCCESS",
        response=response,
        error_message=None,
    )
    return JSONResponse(
        status_code=200,
        content=response.model_dump(mode="json"),
    )
