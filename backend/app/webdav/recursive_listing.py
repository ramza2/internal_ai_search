"""Recursive WebDAV scan (BFS over Depth:1 PROPFIND).

The scan **never** downloads file bodies; it only walks folders. URL paths
are percent-encoded segment-by-segment, child paths are normalized relative
to ``data_sources.webdav_root_path``, and Authorization / passwords are
never returned in failure summaries.

The actual upsert into ``files`` is performed by the calling sync service;
this module is a pure traversal that returns a flat list of items and a
counters dataclass.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from app.webdav.client import join_webdav_url, run_propfind
from app.webdav.listing import normalize_path, parse_depth1_items


_FAILED_PATHS_LIMIT = 20
_WARNINGS_LIMIT = 20


def _canonical_rel(path: str) -> str:
    """Return ``/`` or ``/seg1/seg2`` with no trailing slash (unless root)."""
    p = (path or "/").strip()
    if not p:
        return "/"
    if not p.startswith("/"):
        p = "/" + p
    while "//" in p:
        p = p.replace("//", "/")
    if p != "/" and p.endswith("/"):
        p = p.rstrip("/") or "/"
    return p


def _percent_encode_rel(rel: str) -> str:
    """Encode each path segment of a data-source-relative path. ``/`` → ``""``."""
    parts = [seg for seg in (rel or "").split("/") if seg]
    if not parts:
        return ""
    return "/" + "/".join(quote(seg, safe="") for seg in parts)


def _join_child_rel(folder_rel: str, name: str) -> str:
    f = _canonical_rel(folder_rel or "/")
    n = (name or "").strip().strip("/")
    if not n:
        return f
    if f == "/":
        return "/" + n
    return f + "/" + n


@dataclass(frozen=True)
class ExclusionFilter:
    folder_names: frozenset[str]
    extensions: frozenset[str]
    path_patterns: tuple[str, ...]
    max_file_size_bytes: int | None
    apply: bool
    include_hidden: bool

    def is_hidden_name(self, name: str) -> bool:
        if self.include_hidden:
            return False
        n = (name or "").strip()
        return bool(n) and n.startswith(".")

    def _matches_path_pattern(self, rel_path: str) -> bool:
        if not self.path_patterns:
            return False
        for pat in self.path_patterns:
            if pat and pat in rel_path:
                return True
        return False

    def is_excluded_folder(self, name: str, rel_path: str) -> bool:
        if self.is_hidden_name(name):
            return True
        if not self.apply:
            return False
        ln = (name or "").strip().lower()
        if ln and ln in self.folder_names:
            return True
        return self._matches_path_pattern(rel_path)

    def is_excluded_file(
        self,
        *,
        name: str,
        extension: str | None,
        rel_path: str,
        size_bytes: Any,
    ) -> bool:
        if self.is_hidden_name(name):
            return True
        if not self.apply:
            return False
        ext = (extension or "").strip().lower()
        if ext and ext in self.extensions:
            return True
        if self._matches_path_pattern(rel_path):
            return True
        if self.max_file_size_bytes is not None:
            try:
                sz = int(size_bytes)
            except (TypeError, ValueError):
                sz = None
            if sz is not None and sz > self.max_file_size_bytes:
                return True
        return False


@dataclass
class ScanCounters:
    visited_directories: int = 0
    total_remote_items: int = 0
    excluded_count: int = 0
    failed_count: int = 0
    truncated: bool = False
    failed_paths: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _record_warning(counters: ScanCounters, msg: str) -> None:
    if not msg:
        return
    if len(counters.warnings) >= _WARNINGS_LIMIT:
        return
    counters.warnings.append(msg)


def _record_failed_path(
    counters: ScanCounters, *, remote_path: str, error: str
) -> None:
    counters.failed_count += 1
    if len(counters.failed_paths) < _FAILED_PATHS_LIMIT:
        counters.failed_paths.append(
            {"remote_path": remote_path, "error": error}
        )


def _classify_outcome(
    outcome,
) -> tuple[bool, dict[str, Any] | None, str | None]:
    """Return (ok, fatal_payload_for_start_folder, per_folder_error_summary).

    ``fatal_payload_for_start_folder`` is the dict consumed when the failure
    occurred on the start folder (the caller treats it as a fatal request
    error rather than a per-folder failure).
    """
    if not outcome.reachable:
        err = outcome.error_summary or "Failed to connect to WebDAV server"
        return False, {
            "http_status": outcome.http_status,
            "response_ms": outcome.response_ms,
            "message": "Failed to connect to WebDAV server",
            "error": err,
        }, err
    if not outcome.auth_success:
        err = outcome.error_summary or "HTTP 401 Unauthorized"
        return False, {
            "http_status": outcome.http_status,
            "response_ms": outcome.response_ms,
            "message": "WebDAV authentication failed",
            "error": err,
        }, err
    http = outcome.http_status
    if http == 404:
        err = outcome.error_summary or "HTTP 404 Not Found"
        return False, {
            "http_status": 404,
            "response_ms": outcome.response_ms,
            "message": "WebDAV start path not found",
            "error": err,
        }, err
    if http == 405:
        err = outcome.error_summary or "HTTP 405 Method Not Allowed"
        return False, {
            "http_status": http,
            "response_ms": outcome.response_ms,
            "message": "PROPFIND is not supported for this endpoint",
            "error": err,
        }, err
    if http not in (200, 207):
        err = outcome.error_summary or (
            f"HTTP {http}" if http is not None else "Unknown HTTP status"
        )
        return False, {
            "http_status": http,
            "response_ms": outcome.response_ms,
            "message": "Unexpected WebDAV response",
            "error": err,
        }, err
    return True, None, None


def collect_tree(
    *,
    server_url: str,
    webdav_root_path: str,
    start_path: str,
    max_depth: int,
    max_items: int,
    username: str,
    password: str,
    timeout_seconds: float,
    exclusion: ExclusionFilter,
) -> tuple[list[dict[str, Any]], ScanCounters, dict[str, Any] | None]:
    """BFS over WebDAV folders. Returns (items, counters, fatal_start_error).

    Items carry ``remote_path`` **relative to ``webdav_root_path``** (always
    ``/``-prefixed). A failure on the *start folder* is reported as the
    third element and the caller treats it as a request-level error. Per-
    folder failures during traversal increment ``counters.failed_count``
    and are surfaced via ``counters.failed_paths``.

    ``base_url`` has no trailing slash so ``base_url + encoded`` never
    inserts ``//`` between the WebDAV root and the first path segment; a
    double slash breaks Depth:1 parsing (``href`` prefixes no longer match
    ``root_prefix``) so subfolders would appear empty even when ``max_depth``
    allows deeper walks.
    """
    base_url = join_webdav_url(server_url, webdav_root_path).rstrip("/")
    start_rel = _canonical_rel(start_path or "/")

    counters = ScanCounters()
    items: list[dict[str, Any]] = []
    queue: deque[tuple[str, int]] = deque()
    queue.append((start_rel, 0))
    visited: set[str] = set()

    fatal_start_error: dict[str, Any] | None = None
    is_first = True

    while queue and len(items) < max_items:
        folder_rel, depth = queue.popleft()
        if folder_rel in visited:
            continue
        visited.add(folder_rel)

        encoded = _percent_encode_rel(folder_rel)
        folder_url = base_url if not encoded else base_url + encoded

        outcome = run_propfind(
            webdav_url=folder_url,
            username=username,
            password=password,
            timeout_seconds=timeout_seconds,
            depth="1",
        )

        ok, fatal_candidate, per_folder_err = _classify_outcome(outcome)
        if not ok:
            if is_first:
                fatal_start_error = fatal_candidate
                break
            _record_failed_path(
                counters,
                remote_path=folder_rel,
                error=per_folder_err or "WebDAV folder fetch failed",
            )
            is_first = False
            continue

        parsed, parse_warnings = parse_depth1_items(
            outcome.raw_body, webdav_url=folder_url, http_status=outcome.http_status
        )
        for pw in parse_warnings:
            _record_warning(counters, pw)

        counters.visited_directories += 1
        is_first = False

        for child in parsed:
            counters.total_remote_items += 1
            name = str(child.get("name") or "").strip()
            is_dir = bool(child.get("is_directory"))
            child_rel = _join_child_rel(folder_rel, name)

            if is_dir:
                if exclusion.is_excluded_folder(name, child_rel):
                    counters.excluded_count += 1
                    continue
            else:
                if exclusion.is_excluded_file(
                    name=name,
                    extension=child.get("extension"),
                    rel_path=child_rel,
                    size_bytes=child.get("size_bytes"),
                ):
                    counters.excluded_count += 1
                    continue

            normalized = {
                "name": name or child_rel.rsplit("/", 1)[-1] or child_rel,
                "remote_path": child_rel,
                "href": child.get("href"),
                "is_directory": is_dir,
                "extension": child.get("extension"),
                "size_bytes": child.get("size_bytes"),
                "etag": child.get("etag"),
                "last_modified": child.get("last_modified"),
                "content_type": child.get("content_type"),
            }
            items.append(normalized)

            if len(items) >= max_items:
                counters.truncated = True
                break

            if is_dir and depth < max_depth:
                queue.append((child_rel, depth + 1))

        if counters.truncated:
            break

    if queue and len(items) >= max_items:
        counters.truncated = True

    return items, counters, fatal_start_error
