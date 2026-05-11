"""HTTP WebDAV helpers (PROPFIND with Basic Auth).

Do not log request bodies or Authorization headers. Never expose secrets.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx


PROPFIND_BODY_DEPTH_0 = """<?xml version="1.0" encoding="utf-8" ?>
<d:propfind xmlns:d="DAV:">
  <d:prop>
    <d:displayname/>
    <d:getlastmodified/>
    <d:getetag/>
    <d:getcontentlength/>
    <d:resourcetype/>
  </d:prop>
</d:propfind>
"""

PROPFIND_BODY_DEPTH_1 = """<?xml version="1.0" encoding="utf-8" ?>
<d:propfind xmlns:d="DAV:">
  <d:prop>
    <d:displayname/>
    <d:getlastmodified/>
    <d:getetag/>
    <d:getcontentlength/>
    <d:getcontenttype/>
    <d:resourcetype/>
  </d:prop>
</d:propfind>
"""

# Backwards compatibility with earlier imports / Depth:0 callers
PROPFIND_BODY = PROPFIND_BODY_DEPTH_0


def join_webdav_url(server_url: str, webdav_root_path: str | None) -> str:
    """Join ``server_url`` and ``webdav_root_path`` with correct slashes (no query string)."""
    base = (server_url or "").strip().rstrip("/")
    path = (webdav_root_path or "").strip()
    if path and not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"


@dataclass(frozen=True)
class PropfindOutcome:
    http_status: int | None
    response_ms: int | None
    reachable: bool
    raw_body: bytes
    auth_success: bool
    root_accessible: bool
    error_summary: str | None


def _auth_ok_for_http(status_code: int) -> bool:
    return status_code not in {401, 403}


def _root_ok_http(status_code: int) -> bool:
    return status_code in {200, 207}


def run_propfind(
    *,
    webdav_url: str,
    username: str,
    password: str,
    timeout_seconds: float,
    depth: str = "0",
    propfind_body: str | None = None,
) -> PropfindOutcome:
    """
    Issue a DAV PROPFIND request.

    ``depth``: ``"0"`` or ``"1"`` (other values are passed through as-is).
    ``propfind_body``: overrides the default XML for the chosen depth when set.
    """
    dep = str(depth).strip()
    xml = propfind_body
    if xml is None:
        xml = PROPFIND_BODY_DEPTH_1 if dep == "1" else PROPFIND_BODY_DEPTH_0

    headers = {
        "Depth": dep,
        "Content-Type": "application/xml; charset=utf-8",
        "Accept": "application/xml, text/xml;q=0.9, */*;q=0.1",
    }
    timeout = httpx.Timeout(timeout_seconds)
    auth = httpx.BasicAuth(username, password)
    url = webdav_url
    started = time.perf_counter()

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.request(
                "PROPFIND",
                url,
                headers=headers,
                content=xml.encode("utf-8"),
                auth=auth,
            )
    except httpx.TimeoutException:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return PropfindOutcome(
            http_status=None,
            response_ms=elapsed_ms,
            reachable=False,
            raw_body=b"",
            auth_success=False,
            root_accessible=False,
            error_summary="WebDAV request timed out",
        )
    except httpx.ConnectError:
        return PropfindOutcome(
            http_status=None,
            response_ms=None,
            reachable=False,
            raw_body=b"",
            auth_success=False,
            root_accessible=False,
            error_summary="Failed to connect to WebDAV server",
        )
    except httpx.RequestError:
        return PropfindOutcome(
            http_status=None,
            response_ms=None,
            reachable=False,
            raw_body=b"",
            auth_success=False,
            root_accessible=False,
            error_summary="HTTP request error",
        )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    code = resp.status_code
    body = resp.content or b""
    reachable = True
    auth_success = _auth_ok_for_http(code)
    root_accessible = auth_success and _root_ok_http(code)

    summary: str | None = None
    if code in {401}:
        summary = "HTTP 401 Unauthorized"
    elif code in {403}:
        summary = "HTTP 403 Forbidden"
    elif code == 404:
        summary = "HTTP 404 Not Found"
        root_accessible = False
    elif code == 405:
        summary = "HTTP 405 Method Not Allowed"
        root_accessible = False
    elif code not in {200, 207}:
        summary = f"HTTP {code} {resp.reason_phrase or ''}".strip()
        root_accessible = False

    return PropfindOutcome(
        http_status=code,
        response_ms=elapsed_ms,
        reachable=reachable,
        raw_body=body,
        auth_success=auth_success,
        root_accessible=root_accessible,
        error_summary=summary,
    )
