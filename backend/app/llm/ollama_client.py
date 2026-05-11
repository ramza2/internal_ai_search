"""HTTP client for Ollama REST API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


def tags_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/api/tags"


@dataclass(frozen=True)
class TagsFetchResult:
    """Result of GET /api/tags."""

    ollama_reachable: bool
    """True if TCP/HTTP exchange completed (any status), including read errors after connect."""

    success: bool
    """True if HTTP 200 and a valid models list was parsed."""

    model_names: list[str]
    """Installed model names (empty if not available)."""

    error: str | None


def fetch_model_tags(base_url: str, timeout_seconds: float) -> TagsFetchResult:
    """
    GET /api/tags from Ollama.

    Does not raise: callers use TagsFetchResult for health responses.
    """
    url = tags_url(base_url)
    timeout = httpx.Timeout(timeout_seconds)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
    except httpx.TimeoutException as exc:
        return TagsFetchResult(
            ollama_reachable=False,
            success=False,
            model_names=[],
            error=f"Request timed out after {timeout_seconds}s: {exc}",
        )
    except httpx.ConnectError as exc:
        return TagsFetchResult(
            ollama_reachable=False,
            success=False,
            model_names=[],
            error=f"Failed to connect to Ollama server: {exc}",
        )
    except httpx.RequestError as exc:
        return TagsFetchResult(
            ollama_reachable=False,
            success=False,
            model_names=[],
            error=f"HTTP request error: {exc}",
        )

    if response.status_code != 200:
        return TagsFetchResult(
            ollama_reachable=True,
            success=False,
            model_names=[],
            error=f"Ollama returned HTTP {response.status_code}: {response.text[:500]}",
        )

    try:
        payload: dict[str, Any] = response.json()
    except ValueError as exc:
        return TagsFetchResult(
            ollama_reachable=True,
            success=False,
            model_names=[],
            error=f"Invalid JSON from Ollama: {exc}",
        )

    models = payload.get("models")
    if not isinstance(models, list):
        return TagsFetchResult(
            ollama_reachable=True,
            success=False,
            model_names=[],
            error="Ollama response missing or invalid 'models' array",
        )

    names: list[str] = []
    for item in models:
        if isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and name:
                names.append(name)

    return TagsFetchResult(
        ollama_reachable=True,
        success=True,
        model_names=names,
        error=None,
    )
