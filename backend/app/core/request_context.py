"""Extract client-facing request metadata for audit logs (Step 20)."""

from __future__ import annotations

from fastapi import Request


def get_client_ip(request: Request) -> str | None:
    """Best-effort client IP (``X-Forwarded-For`` first hop, else ``request.client``)."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        return first[:128] if first else None
    if request.client and request.client.host:
        return request.client.host[:128]
    return None


def get_request_audit_meta(request: Request) -> tuple[str | None, str | None, str, str]:
    """Return ``(ip_address, user_agent, request_url, request_method)``.

    ``request_url`` is the URL path only (no query string) so secrets are
    not copied from ``?`` parameters into ``action_logs``.
    """
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent")
    if ua is not None:
        ua = ua[:4000]
    url = request.url.path
    return ip, ua, url, request.method.upper()


__all__ = ["get_client_ip", "get_request_audit_meta"]
