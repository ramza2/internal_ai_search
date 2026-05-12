"""WebDAV file download (HTTP GET with Basic Auth).

The byte body is read fully into memory; callers enforce their own size
ceiling via ``max_bytes`` (the helper hard-stops streaming once the limit
is crossed and reports ``truncated=True``).

Never logs Authorization headers, credential plaintext, or the WebDAV URL
embedded with credentials. Error summaries are short HTTP-status-style
strings so they can be safely persisted to ``scan_jobs.error_message`` or
``scan_failures.error_message``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import quote

import httpx


@dataclass(frozen=True)
class DownloadOutcome:
    success: bool
    http_status: int | None
    response_ms: int | None
    body: bytes
    truncated: bool
    auth_failed: bool
    not_found: bool
    error_summary: str | None


def build_file_url(
    *, server_url: str, webdav_root_path: str, remote_path: str
) -> str:
    """Compose the WebDAV file URL with each path segment percent-encoded.

    ``remote_path`` is the data-source-relative path stored on the
    ``files`` row (always begins with ``/``); ``webdav_root_path`` is the
    DAV root prefix configured on the data source. Each segment is encoded
    independently so reserved characters in a file name (`#`, `?`, space,
    Korean characters, …) are escaped without touching the path
    separators.
    """
    base = (server_url or "").strip().rstrip("/")
    root = (webdav_root_path or "").strip()
    if root and not root.startswith("/"):
        root = "/" + root
    if root.endswith("/") and root != "/":
        root = root.rstrip("/")
    rel = (remote_path or "/").strip()
    if not rel.startswith("/"):
        rel = "/" + rel
    parts = [seg for seg in rel.split("/") if seg]
    encoded_rel = "/" + "/".join(quote(seg, safe="") for seg in parts) if parts else ""
    return f"{base}{root}{encoded_rel}"


def _short_status_summary(status_code: int, reason: str | None) -> str:
    text = (reason or "").strip()
    if text:
        return f"HTTP {status_code} {text}"
    return f"HTTP {status_code}"


def download_file_bytes(
    *,
    server_url: str,
    webdav_root_path: str,
    remote_path: str,
    username: str,
    password: str,
    timeout_seconds: float,
    max_bytes: int | None = None,
) -> DownloadOutcome:
    """GET a WebDAV file with Basic Auth and return the byte body.

    - ``http_status`` is ``None`` for transport-level failures (timeout /
      connect error). ``error_summary`` carries a short, non-secret
      description in every failure case.
    - When ``max_bytes`` is set, streaming stops as soon as the running
      byte count exceeds the cap; the outcome reports ``truncated=True``
      and ``success=False`` with the partial body discarded.
    """
    url = build_file_url(
        server_url=server_url,
        webdav_root_path=webdav_root_path,
        remote_path=remote_path,
    )
    timeout = httpx.Timeout(timeout_seconds)
    auth = httpx.BasicAuth(username, password)
    headers = {"Accept": "*/*"}
    started = time.perf_counter()

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            with client.stream(
                "GET", url, headers=headers, auth=auth
            ) as resp:
                code = resp.status_code
                if code == 401:
                    return DownloadOutcome(
                        success=False,
                        http_status=code,
                        response_ms=int(
                            (time.perf_counter() - started) * 1000
                        ),
                        body=b"",
                        truncated=False,
                        auth_failed=True,
                        not_found=False,
                        error_summary="HTTP 401 Unauthorized",
                    )
                if code == 403:
                    return DownloadOutcome(
                        success=False,
                        http_status=code,
                        response_ms=int(
                            (time.perf_counter() - started) * 1000
                        ),
                        body=b"",
                        truncated=False,
                        auth_failed=True,
                        not_found=False,
                        error_summary="HTTP 403 Forbidden",
                    )
                if code == 404:
                    return DownloadOutcome(
                        success=False,
                        http_status=code,
                        response_ms=int(
                            (time.perf_counter() - started) * 1000
                        ),
                        body=b"",
                        truncated=False,
                        auth_failed=False,
                        not_found=True,
                        error_summary="HTTP 404 Not Found",
                    )
                if code != 200:
                    return DownloadOutcome(
                        success=False,
                        http_status=code,
                        response_ms=int(
                            (time.perf_counter() - started) * 1000
                        ),
                        body=b"",
                        truncated=False,
                        auth_failed=False,
                        not_found=False,
                        error_summary=_short_status_summary(
                            code, resp.reason_phrase
                        ),
                    )

                buf = bytearray()
                truncated = False
                cap = int(max_bytes) if max_bytes is not None else None
                try:
                    for chunk in resp.iter_bytes():
                        if not chunk:
                            continue
                        if cap is not None and len(buf) + len(chunk) > cap:
                            truncated = True
                            break
                        buf.extend(chunk)
                except httpx.RequestError as exc:
                    return DownloadOutcome(
                        success=False,
                        http_status=code,
                        response_ms=int(
                            (time.perf_counter() - started) * 1000
                        ),
                        body=b"",
                        truncated=False,
                        auth_failed=False,
                        not_found=False,
                        error_summary=f"Streaming error: {type(exc).__name__}",
                    )

                elapsed_ms = int((time.perf_counter() - started) * 1000)
                if truncated:
                    return DownloadOutcome(
                        success=False,
                        http_status=code,
                        response_ms=elapsed_ms,
                        body=b"",
                        truncated=True,
                        auth_failed=False,
                        not_found=False,
                        error_summary=(
                            "Downloaded size exceeded max_file_size_bytes"
                        ),
                    )
                return DownloadOutcome(
                    success=True,
                    http_status=code,
                    response_ms=elapsed_ms,
                    body=bytes(buf),
                    truncated=False,
                    auth_failed=False,
                    not_found=False,
                    error_summary=None,
                )
    except httpx.TimeoutException:
        return DownloadOutcome(
            success=False,
            http_status=None,
            response_ms=int((time.perf_counter() - started) * 1000),
            body=b"",
            truncated=False,
            auth_failed=False,
            not_found=False,
            error_summary="WebDAV download timed out",
        )
    except httpx.ConnectError:
        return DownloadOutcome(
            success=False,
            http_status=None,
            response_ms=None,
            body=b"",
            truncated=False,
            auth_failed=False,
            not_found=False,
            error_summary="Failed to connect to WebDAV server",
        )
    except httpx.RequestError as exc:
        return DownloadOutcome(
            success=False,
            http_status=None,
            response_ms=None,
            body=b"",
            truncated=False,
            auth_failed=False,
            not_found=False,
            error_summary=f"HTTP request error: {type(exc).__name__}",
        )
