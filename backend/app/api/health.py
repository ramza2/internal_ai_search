from fastapi import APIRouter

from app.core.config import settings
from app.db.health import check_db_health
from app.db.vector_health import check_vector_db_health
from app.embedding.health import check_embedding_health
from app.llm.health import check_ollama_health


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.service_name,
    }


@router.get("/health/db")
def health_db() -> dict:
    db_health = check_db_health()

    return {
        "status": "ok" if db_health["ok"] else "error",
        "service": settings.service_name,
        "db": db_health,
    }


@router.get("/health/llm")
def health_llm() -> dict:
    """Ollama reachability and configured LLM model availability."""
    try:
        return check_ollama_health(settings)
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "status": "error",
            "ollama_base_url": settings.ollama_base_url,
            "configured_model": settings.ollama_model,
            "ollama_reachable": False,
            "model_available": False,
            "available_models": [],
            "message": "Unexpected error while checking Ollama",
            "error": str(exc),
        }


@router.get("/health/embedding")
def health_embedding() -> dict:
    """Ollama embedding: test encode and verify dimension (e.g. 1024 for bge-m3)."""
    try:
        return check_embedding_health(settings)
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "status": "error",
            "provider": settings.embedding_provider,
            "model": settings.embedding_model,
            "expected_dimension": settings.embedding_dimension,
            "actual_dimension": None,
            "dimension_matched": False,
            "message": "Unexpected error while checking embedding model",
            "error": str(exc),
        }


@router.get("/health/vector-db")
def health_vector_db() -> dict:
    """Embedding + PostgreSQL pgvector temp insert and cosine similarity smoke test."""
    try:
        return check_vector_db_health(settings)
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "status": "error",
            "embedding_model": settings.embedding_model,
            "expected_dimension": settings.embedding_dimension,
            "generated_dimension": None,
            "db_insert_success": False,
            "db_vector_dimension": None,
            "dimension_matched": False,
            "similarity_search_success": False,
            "message": "Unexpected error while running pgvector smoke test",
            "error": str(exc),
            "schema_check": None,
        }
