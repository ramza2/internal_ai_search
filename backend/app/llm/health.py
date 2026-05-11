"""Ollama connectivity and configured model availability."""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.llm.ollama_client import fetch_model_tags


def _model_matches_configured(available_name: str, configured: str) -> bool:
    """Match Ollama tag (e.g. gemma3:latest) to configured base name (e.g. gemma3)."""
    if not available_name or not configured:
        return False
    if available_name == configured:
        return True
    base = available_name.split(":", 1)[0]
    return base == configured


def check_ollama_health(settings: Settings) -> dict[str, Any]:
    """
    Check Ollama server reachability and whether OLLAMA_MODEL is present.

    Never raises: suitable for health endpoints so the API process stays up.
    """
    base_url = settings.ollama_base_url
    configured = settings.ollama_model
    timeout = settings.ollama_timeout_seconds

    result = fetch_model_tags(base_url, timeout)

    if not result.ollama_reachable:
        return {
            "status": "error",
            "ollama_base_url": base_url,
            "configured_model": configured,
            "ollama_reachable": False,
            "model_available": False,
            "available_models": [],
            "message": "Failed to connect to Ollama server",
            "error": result.error or "Unknown error",
        }

    if not result.success:
        return {
            "status": "error",
            "ollama_base_url": base_url,
            "configured_model": configured,
            "ollama_reachable": True,
            "model_available": False,
            "available_models": [],
            "message": "Ollama server responded but /api/tags could not be read",
            "error": result.error or "Unknown error",
        }

    names = result.model_names
    model_available = any(_model_matches_configured(n, configured) for n in names)

    if model_available:
        return {
            "status": "ok",
            "ollama_base_url": base_url,
            "configured_model": configured,
            "ollama_reachable": True,
            "model_available": True,
            "available_models": names,
            "message": "Ollama connection is healthy",
        }

    return {
        "status": "error",
        "ollama_base_url": base_url,
        "configured_model": configured,
        "ollama_reachable": True,
        "model_available": False,
        "available_models": names,
        "message": "Configured model is not available",
        "error": f"Model {configured!r} not found among installed models",
    }
