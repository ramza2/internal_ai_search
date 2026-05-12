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


@dataclass(frozen=True)
class BatchEmbeddingResult:
    """Outcome of a single batch call.

    - ``vectors[i] is None`` when the i-th text could not be embedded (the
      orchestrator marks the corresponding chunk as ``FAILED`` while
      letting the rest of the batch land in the database).
    - ``error`` is a short, non-secret string describing why the *batch*
      itself short-circuited (e.g. ``"Failed to connect to Ollama"``);
      the per-text error appears in ``per_text_errors[i]`` when set.
    """

    success: bool
    vectors: list[list[float] | None]
    error: str | None
    per_text_errors: list[str | None]


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


def _extract_vectors_from_batch_payload(
    payload: dict[str, Any], *, expected_count: int
) -> list[list[float]] | None:
    """Parse a list of embedding vectors from a batched Ollama response.

    Accepts the modern ``{"embeddings": [[...], [...]]}`` shape and the
    OpenAI-compatible ``{"data": [{"embedding": [...]}, ...]}`` shape.
    Returns ``None`` when the response does not look like a batched
    payload of the expected length.
    """
    embeddings = payload.get("embeddings")
    if isinstance(embeddings, list) and len(embeddings) == expected_count:
        out: list[list[float]] = []
        for raw in embeddings:
            if not isinstance(raw, list) or not raw:
                return None
            try:
                out.append([float(x) for x in raw])
            except (TypeError, ValueError):
                return None
        return out

    data = payload.get("data")
    if isinstance(data, list) and len(data) == expected_count:
        out2: list[list[float]] = []
        for item in data:
            if not isinstance(item, dict):
                return None
            emb = item.get("embedding")
            if not isinstance(emb, list) or not emb:
                return None
            try:
                out2.append([float(x) for x in emb])
            except (TypeError, ValueError):
                return None
        return out2

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


def create_embeddings_batch(
    base_url: str,
    model: str,
    texts: list[str],
    timeout_seconds: float,
) -> BatchEmbeddingResult:
    """Embed several texts in one HTTP round-trip when the server supports it.

    Strategy:

    1. POST ``/api/embed`` with ``input=[texts...]``. If the response
       returns a list of N vectors that line up with the request length,
       use them directly.
    2. Otherwise, fall back to N independent single-text calls via
       :func:`create_embedding`. The orchestrator does not need to
       distinguish — both paths return aligned ``vectors[i]`` slots.

    The function does **not** raise. A connection-level failure on the
    batch attempt is swallowed and the fallback path runs anyway so a
    single misbehaving call cannot poison the whole job.
    """
    if not texts:
        return BatchEmbeddingResult(True, [], None, [])

    timeout = httpx.Timeout(timeout_seconds)
    body: dict[str, Any] = {"model": model, "input": texts}

    try:
        with httpx.Client(timeout=timeout) as client:
            status, data, err = _post_json(client, _embed_url(base_url), body)
            if status == 200 and data is not None:
                vectors = _extract_vectors_from_batch_payload(
                    data, expected_count=len(texts)
                )
                if vectors is not None:
                    return BatchEmbeddingResult(
                        True,
                        list(vectors),
                        None,
                        [None] * len(texts),
                    )
            # Else: server doesn't support batched input or returned an
            # unparseable shape — fall through to per-text calls.
    except httpx.TimeoutException as exc:
        return BatchEmbeddingResult(
            False,
            [None] * len(texts),
            f"Embedding batch request timed out: {exc}",
            [None] * len(texts),
        )
    except httpx.ConnectError as exc:
        return BatchEmbeddingResult(
            False,
            [None] * len(texts),
            f"Failed to connect to Ollama: {exc}",
            [None] * len(texts),
        )
    except httpx.RequestError:
        # Recover with the per-text fallback rather than failing the whole
        # batch — the next loop will surface individual errors.
        pass
    except Exception:  # pragma: no cover - defensive
        pass

    # Per-text fallback (also covers servers that don't accept a list).
    vectors_out: list[list[float] | None] = []
    per_errors: list[str | None] = []
    for text in texts:
        single = create_embedding(
            base_url=base_url,
            model=model,
            text=text,
            timeout_seconds=timeout_seconds,
        )
        if single.success and single.vector is not None:
            vectors_out.append(single.vector)
            per_errors.append(None)
        else:
            vectors_out.append(None)
            per_errors.append(single.error or "Unknown embedding error")
    overall_ok = all(v is not None for v in vectors_out)
    return BatchEmbeddingResult(
        overall_ok,
        vectors_out,
        None,
        per_errors,
    )
