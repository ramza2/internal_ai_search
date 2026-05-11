"""Ollama embedding HTTP client (/api/embed with optional /api/embeddings fallback)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class EmbeddingCallResult:
    success: bool
    vector: list[float] | None
    error: str | None


def _embed_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/api/embed"


def _embeddings_legacy_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/api/embeddings"


def _extract_vector_from_payload(payload: dict[str, Any]) -> list[float] | None:
    """Parse embedding vector from Ollama or compatible JSON (defensive)."""
    embeddings = payload.get("embeddings")
    if isinstance(embeddings, list) and embeddings:
        first = embeddings[0]
        if isinstance(first, list) and first:
            try:
                return [float(x) for x in first]
            except (TypeError, ValueError):
                pass

    single = payload.get("embedding")
    if isinstance(single, list) and single:
        try:
            return [float(x) for x in single]
        except (TypeError, ValueError):
            pass

    data = payload.get("data")
    if isinstance(data, list) and data:
        item = data[0]
        if isinstance(item, dict):
            emb = item.get("embedding")
            if isinstance(emb, list) and emb:
                try:
                    return [float(x) for x in emb]
                except (TypeError, ValueError):
                    pass

    return None


def _post_json(
    client: httpx.Client,
    url: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any] | None, str | None]:
    """Returns (status_code, json_dict_or_none, error_message)."""
    try:
        response = client.post(url, json=body)
    except httpx.RequestError as exc:
        return -1, None, str(exc)

    try:
        data = response.json()
    except ValueError:
        return response.status_code, None, f"Invalid JSON (HTTP {response.status_code})"

    if not isinstance(data, dict):
        return response.status_code, None, f"Unexpected JSON type (HTTP {response.status_code})"

    return response.status_code, data, None


def create_embedding(
    base_url: str,
    model: str,
    text: str,
    timeout_seconds: float,
) -> EmbeddingCallResult:
    """
    Call Ollama embedding API.

    Tries POST /api/embed with ``input``; if no usable vector, tries POST /api/embeddings with ``prompt``.
    Does not raise.
    """
    timeout = httpx.Timeout(timeout_seconds)
    embed_body: dict[str, Any] = {"model": model, "input": text}
    legacy_body: dict[str, Any] = {"model": model, "prompt": text}

    notes: list[str] = []

    try:
        with httpx.Client(timeout=timeout) as client:
            status, data, err = _post_json(client, _embed_url(base_url), embed_body)
            if status == -1:
                notes.append(f"/api/embed: {err}")
            elif status == 200 and data is not None:
                vec = _extract_vector_from_payload(data)
                if vec is not None:
                    return EmbeddingCallResult(True, vec, None)
                notes.append("/api/embed: HTTP 200 but no parseable embedding")
            else:
                notes.append(f"/api/embed: HTTP {status}" + (f" ({err})" if err else ""))

            status2, data2, err2 = _post_json(
                client, _embeddings_legacy_url(base_url), legacy_body
            )
            if status2 == -1:
                notes.append(f"/api/embeddings: {err2}")
            elif status2 == 200 and data2 is not None:
                vec2 = _extract_vector_from_payload(data2)
                if vec2 is not None:
                    return EmbeddingCallResult(True, vec2, None)
                notes.append("/api/embeddings: HTTP 200 but no parseable embedding")
            else:
                notes.append(f"/api/embeddings: HTTP {status2}" + (f" ({err2})" if err2 else ""))

    except httpx.TimeoutException as exc:
        return EmbeddingCallResult(False, None, f"Embedding request timed out: {exc}")
    except httpx.ConnectError as exc:
        return EmbeddingCallResult(False, None, f"Failed to connect to Ollama: {exc}")
    except httpx.RequestError as exc:
        return EmbeddingCallResult(False, None, f"HTTP error: {exc}")
    except Exception as exc:  # pragma: no cover - defensive
        return EmbeddingCallResult(False, None, f"Unexpected error: {exc}")

    return EmbeddingCallResult(False, None, "; ".join(notes))
