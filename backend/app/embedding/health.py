"""Embedding model health: single test encode + dimension check."""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.embedding.ollama_embedding_client import create_embedding


def check_embedding_health(settings: Settings) -> dict[str, Any]:
    """
    Run a test embedding and verify vector length matches EMBEDDING_DIMENSION.

    Never raises.
    """
    provider = (settings.embedding_provider or "").strip().lower()
    model = settings.embedding_model
    expected = settings.embedding_dimension
    test_text = settings.embedding_test_text
    timeout = settings.embedding_timeout_seconds
    base = settings.ollama_base_url

    if provider != "ollama":
        return {
            "status": "error",
            "provider": settings.embedding_provider,
            "model": model,
            "expected_dimension": expected,
            "actual_dimension": None,
            "dimension_matched": False,
            "message": "Unsupported embedding provider",
            "error": f"Only provider 'ollama' is supported in this step; got {settings.embedding_provider!r}",
        }

    result = create_embedding(
        base_url=base,
        model=model,
        text=test_text,
        timeout_seconds=timeout,
    )

    if not result.success or result.vector is None:
        return {
            "status": "error",
            "provider": "ollama",
            "model": model,
            "expected_dimension": expected,
            "actual_dimension": None,
            "dimension_matched": False,
            "message": "Failed to generate embedding",
            "error": result.error or "Unknown error",
        }

    actual = len(result.vector)
    matched = actual == expected

    if not matched:
        return {
            "status": "error",
            "provider": "ollama",
            "model": model,
            "expected_dimension": expected,
            "actual_dimension": actual,
            "dimension_matched": False,
            "message": "Embedding dimension mismatch",
            "error": f"Expected {expected} dimensions, got {actual}",
        }

    return {
        "status": "ok",
        "provider": "ollama",
        "model": model,
        "expected_dimension": expected,
        "actual_dimension": actual,
        "dimension_matched": True,
        "test_text": test_text,
        "message": "Embedding model is healthy",
    }
