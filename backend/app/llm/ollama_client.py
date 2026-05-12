"""HTTP client for Ollama REST API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


def tags_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/api/tags"


def generate_url(base_url: str) -> str:
    """``/api/generate`` URL builder — Step 16 RAG answer generation."""
    base = base_url.rstrip("/")
    return f"{base}/api/generate"


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


@dataclass(frozen=True)
class GenerateResult:
    """Outcome of POST /api/generate (non-streaming).

    ``success`` is ``True`` only when Ollama returned HTTP 200 *and* a
    non-empty ``response`` field. ``error`` carries a short, non-secret
    summary suitable for surfacing in JSON error envelopes — the
    project's policy bans logging or returning prompt bodies.
    """

    success: bool
    answer: str | None
    model: str | None
    finish_reason: str | None
    error: str | None
    http_status: int | None


def _parse_generate_payload(
    payload: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Pull ``response`` + optional ``done_reason`` from an Ollama JSON body.

    Returns ``(answer, finish_reason)``. ``answer`` is ``None`` when the
    payload doesn't look like a valid non-streamed generation response,
    so the caller can surface ``RESPONSE_PARSE_FAILED``.
    """
    text = payload.get("response")
    if not isinstance(text, str) or not text.strip():
        return None, None
    reason = payload.get("done_reason")
    if not isinstance(reason, str):
        reason = None
    return text, reason


def generate_completion(
    *,
    base_url: str,
    model: str,
    prompt: str,
    timeout_seconds: float,
    temperature: float | None = None,
    num_predict: int | None = None,
    extra_options: dict[str, Any] | None = None,
) -> GenerateResult:
    """POST /api/generate with ``stream=false`` and return the answer text.

    Designed for the Step-16 RAG endpoint: a single prompt in, a single
    answer out. The function **never raises** — every network /
    timeout / parsing failure becomes a :class:`GenerateResult` with
    ``success=False`` and a short ``error`` blurb.

    Caller controls ``timeout_seconds`` so a slow LLM never hangs a
    web worker indefinitely; the same value is reused for the
    underlying ``httpx`` connect / read deadlines.
    """
    timeout = httpx.Timeout(timeout_seconds)
    options: dict[str, Any] = {}
    if temperature is not None:
        options["temperature"] = float(temperature)
    if num_predict is not None:
        options["num_predict"] = int(num_predict)
    if extra_options:
        for k, v in extra_options.items():
            if k not in options:
                options[k] = v

    body: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    if options:
        body["options"] = options

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(generate_url(base_url), json=body)
    except httpx.TimeoutException as exc:
        return GenerateResult(
            success=False,
            answer=None,
            model=model,
            finish_reason=None,
            error=f"LLM request timed out after {timeout_seconds}s: {exc}",
            http_status=None,
        )
    except httpx.ConnectError as exc:
        return GenerateResult(
            success=False,
            answer=None,
            model=model,
            finish_reason=None,
            error=f"Failed to connect to Ollama: {exc}",
            http_status=None,
        )
    except httpx.RequestError as exc:
        return GenerateResult(
            success=False,
            answer=None,
            model=model,
            finish_reason=None,
            error=f"HTTP request error: {exc}",
            http_status=None,
        )

    if response.status_code != 200:
        return GenerateResult(
            success=False,
            answer=None,
            model=model,
            finish_reason=None,
            error=f"Ollama returned HTTP {response.status_code}",
            http_status=response.status_code,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        return GenerateResult(
            success=False,
            answer=None,
            model=model,
            finish_reason=None,
            error=f"Invalid JSON from Ollama: {exc}",
            http_status=response.status_code,
        )

    if not isinstance(payload, dict):
        return GenerateResult(
            success=False,
            answer=None,
            model=model,
            finish_reason=None,
            error="Unexpected JSON shape from Ollama",
            http_status=response.status_code,
        )

    answer, finish_reason = _parse_generate_payload(payload)
    if answer is None:
        return GenerateResult(
            success=False,
            answer=None,
            model=str(payload.get("model") or model),
            finish_reason=finish_reason,
            error="Ollama returned an empty or unparseable 'response' field",
            http_status=response.status_code,
        )

    return GenerateResult(
        success=True,
        answer=answer,
        model=str(payload.get("model") or model),
        finish_reason=finish_reason,
        error=None,
        http_status=response.status_code,
    )
