"""Unit tests for sync-tree FULL vs LIMITED scope resolution."""

from __future__ import annotations

from app.services.sync_tree_scope import (
    SCAN_SCOPE_FULL,
    SCAN_SCOPE_LIMITED,
    normalize_scan_scope,
    resolve_sync_tree_limits,
)


def test_normalize_scan_scope_defaults_to_limited() -> None:
    assert normalize_scan_scope(None) == SCAN_SCOPE_LIMITED
    assert normalize_scan_scope("") == SCAN_SCOPE_LIMITED
    assert normalize_scan_scope("full") == SCAN_SCOPE_FULL


def test_resolve_full_ignores_user_depth_items() -> None:
    md, mi, is_full = resolve_sync_tree_limits(SCAN_SCOPE_FULL, 3, 5000)
    assert is_full is True
    assert md > 20
    assert mi > 50_000


def test_resolve_limited_applies_defaults_and_clamps() -> None:
    md, mi, is_full = resolve_sync_tree_limits(SCAN_SCOPE_LIMITED, None, None)
    assert is_full is False
    assert md == 3
    assert mi == 5000

    md2, mi2, _ = resolve_sync_tree_limits(SCAN_SCOPE_LIMITED, 99, 99_999)
    assert md2 == 20
    assert mi2 == 50_000


def test_emergency_max_items_on_full() -> None:
    _, mi, is_full = resolve_sync_tree_limits(
        SCAN_SCOPE_FULL, None, None, emergency_max_items=12_345
    )
    assert is_full is True
    assert mi == 12_345
