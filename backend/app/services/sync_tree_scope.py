"""scan_scope (FULL vs LIMITED) and effective sync-tree depth/item limits."""

from __future__ import annotations

from typing import Any

from app.core.config import Settings

SCAN_SCOPE_LIMITED = "LIMITED"
SCAN_SCOPE_FULL = "FULL"

SYNC_FULL_BLOCKED_MESSAGE = (
    "전체 저장소 처리는 백그라운드 파이프라인에서 실행해주세요."
)

# Effective caps when FULL (no user-facing depth/item limit).
EFFECTIVE_UNBOUNDED_DEPTH = 1_000_000
EFFECTIVE_UNBOUNDED_ITEMS = 10_000_000

LIMITED_DEPTH_DEFAULT = 3
LIMITED_ITEMS_DEFAULT = 5000
LIMITED_DEPTH_CEILING = 20
LIMITED_ITEMS_CEILING = 50_000

SERVER_MAX_PROCESS_FILE_BYTES = 256 * 1024 * 1024


def normalize_scan_scope(raw: Any) -> str:
    s = str(raw or "").strip().upper()
    return SCAN_SCOPE_FULL if s == SCAN_SCOPE_FULL else SCAN_SCOPE_LIMITED


def emergency_max_items_from_settings(settings: Settings) -> int:
    """0 means no emergency cap (only internal unbounded ceiling)."""
    try:
        return max(0, int(getattr(settings, "sync_tree_emergency_max_items", 0) or 0))
    except (TypeError, ValueError):
        return 0


def resolve_sync_tree_limits(
    scan_scope: str,
    max_depth: int | None,
    max_items: int | None,
    *,
    emergency_max_items: int = 0,
) -> tuple[int, int, bool]:
    """Return ``(effective_max_depth, effective_max_items, is_full_scope)``."""
    scope = normalize_scan_scope(scan_scope)
    if scope == SCAN_SCOPE_FULL:
        eff_depth = EFFECTIVE_UNBOUNDED_DEPTH
        if emergency_max_items > 0:
            eff_items = emergency_max_items
        else:
            eff_items = EFFECTIVE_UNBOUNDED_ITEMS
        return eff_depth, eff_items, True

    md = LIMITED_DEPTH_DEFAULT if max_depth is None else int(max_depth)
    mi = LIMITED_ITEMS_DEFAULT if max_items is None else int(max_items)
    if md < 0:
        md = 0
    if md > LIMITED_DEPTH_CEILING:
        md = LIMITED_DEPTH_CEILING
    if mi < 1:
        mi = 1
    if mi > LIMITED_ITEMS_CEILING:
        mi = LIMITED_ITEMS_CEILING
    return md, mi, False


def parse_sync_job_params(params: dict[str, Any] | None) -> tuple[str, str, int | None, int | None]:
    p = params or {}
    start_path = str(p.get("start_path") if p.get("start_path") is not None else "/").strip() or "/"
    scope = normalize_scan_scope(p.get("scan_scope"))
    md_raw = p.get("max_depth")
    mi_raw = p.get("max_items")
    md: int | None
    mi: int | None
    if md_raw is None:
        md = None
    else:
        try:
            md = int(md_raw)
        except (TypeError, ValueError):
            md = None
    if mi_raw is None:
        mi = None
    else:
        try:
            mi = int(mi_raw)
        except (TypeError, ValueError):
            mi = None
    return start_path, scope, md, mi


__all__ = [
    "EFFECTIVE_UNBOUNDED_DEPTH",
    "EFFECTIVE_UNBOUNDED_ITEMS",
    "LIMITED_DEPTH_CEILING",
    "LIMITED_DEPTH_DEFAULT",
    "LIMITED_ITEMS_CEILING",
    "LIMITED_ITEMS_DEFAULT",
    "SCAN_SCOPE_FULL",
    "SCAN_SCOPE_LIMITED",
    "SERVER_MAX_PROCESS_FILE_BYTES",
    "SYNC_FULL_BLOCKED_MESSAGE",
    "emergency_max_items_from_settings",
    "normalize_scan_scope",
    "parse_sync_job_params",
    "resolve_sync_tree_limits",
]
