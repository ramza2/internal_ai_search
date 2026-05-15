"""PIPELINE parent progress / summary derived from child ``scan_jobs`` rows (no schema changes)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

_ACTIVE = frozenset({"PENDING", "RUNNING", "CANCELLING"})
_TERMINAL_OK = frozenset({"COMPLETED", "PARTIAL"})
_FAILED = frozenset({"FAILED"})
_CANCELLED = frozenset({"CANCELLED", "STOPPED"})


def pipeline_steps_from_job_params(job_params: Any) -> list[str] | None:
    if not isinstance(job_params, dict):
        return None
    raw = job_params.get("steps")
    if not isinstance(raw, list) or not raw:
        return None
    out = [str(s).strip().upper() for s in raw if str(s).strip()]
    return out or None


def _ts_key(v: Any) -> tuple[int, str]:
    if isinstance(v, datetime):
        return (int(v.timestamp() * 1_000_000)), ""
    return (0, str(v or ""))


def canonical_child_by_step(steps: list[str], children_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Earliest ``created_at`` (then ``id``) child per pipeline step (``job_type`` matches step code)."""
    buckets: dict[str, list[dict[str, Any]]] = {s: [] for s in steps}
    for row in children_rows:
        jt = str(row.get("job_type") or "").strip().upper()
        if jt in buckets:
            buckets[jt].append(row)

    out: dict[str, dict[str, Any]] = {}
    for step in steps:
        rows = buckets.get(step) or []
        if not rows:
            continue
        rows.sort(
            key=lambda r: (
                _ts_key(r.get("created_at")),
                str(r.get("id") or ""),
            )
        )
        out[step] = rows[0]
    return out


def _step_fraction(status: str, progress_percent: Any) -> float:
    st = (status or "").strip().upper()
    if st in _TERMINAL_OK:
        return 1.0
    if st == "RUNNING":
        if progress_percent is None:
            return 0.0
        try:
            p = float(progress_percent)
        except (TypeError, ValueError):
            return 0.0
        if p != p:
            return 0.0
        return max(0.0, min(1.0, p / 100.0))
    if st == "PENDING":
        return 0.0
    if st in _FAILED or st in _CANCELLED:
        return 0.0
    return 0.0


def _pick_current_pipeline_step(steps: list[str], canon: dict[str, dict[str, Any]]) -> str | None:
    """First frontier step in pipeline order; ``None`` when each step has a COMPLETED/PARTIAL child."""
    for step in steps:
        ch = canon.get(step)
        if not ch:
            return step
        st = str(ch.get("status") or "").strip().upper()
        if st in _TERMINAL_OK:
            continue
        return step
    return None


def compute_pipeline_summary_dict(
    *,
    steps: list[str],
    children_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a dict suitable for :class:`AdminJobChildrenSummary` and list/detail overlays."""
    n = len(steps)
    if n == 0:
        return {
            "total_steps": 0,
            "completed_steps": 0,
            "running_steps": 0,
            "pending_steps": 0,
            "failed_steps": 0,
            "cancelled_steps": 0,
            "partial_steps": 0,
            "progress_percent": 0.0,
            "current_step": None,
            "terminal_steps": 0,
            "completed_child_steps": 0,
            "failed_child_steps": 0,
            "partial_child_steps": 0,
            "cancelled_child_steps": 0,
        }

    canon = canonical_child_by_step(steps, children_rows)
    frac_sum = 0.0
    completed_steps = running_steps = pending_steps = 0
    failed_steps = cancelled_steps = partial_steps = 0
    completed_child = failed_child = partial_child = cancelled_child = 0
    terminal_steps = 0

    for step in steps:
        ch = canon.get(step)
        if not ch:
            pending_steps += 1
            frac_sum += 0.0
            continue
        st = str(ch.get("status") or "").strip().upper()
        frac_sum += _step_fraction(st, ch.get("progress_percent"))

        if st == "PENDING":
            pending_steps += 1
            continue
        if st == "RUNNING":
            running_steps += 1
            continue
        if st == "CANCELLING":
            running_steps += 1
            continue
        if st == "COMPLETED":
            completed_steps += 1
            completed_child += 1
            terminal_steps += 1
            continue
        if st == "PARTIAL":
            partial_steps += 1
            partial_child += 1
            terminal_steps += 1
            continue
        if st in _FAILED:
            failed_steps += 1
            failed_child += 1
            terminal_steps += 1
            continue
        if st in _CANCELLED:
            cancelled_steps += 1
            cancelled_child += 1
            terminal_steps += 1
            continue

        terminal_steps += 1

    progress_percent = round((frac_sum / float(n)) * 100.0, 2) if n else 0.0
    current_step = _pick_current_pipeline_step(steps, canon)

    return {
        "total_steps": n,
        "completed_steps": completed_steps,
        "running_steps": running_steps,
        "pending_steps": pending_steps,
        "failed_steps": failed_steps,
        "cancelled_steps": cancelled_steps,
        "partial_steps": partial_steps,
        "progress_percent": progress_percent,
        "current_step": current_step,
        "terminal_steps": terminal_steps,
        "completed_child_steps": completed_child,
        "failed_child_steps": failed_child,
        "partial_child_steps": partial_child,
        "cancelled_child_steps": cancelled_child,
    }


def overlay_pipeline_counters_on_job_dict(row: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    """Interpret ``*_files`` columns as per-step counters for PIPELINE rows (API-only)."""
    out = dict(row)
    out["progress_percent"] = summary.get("progress_percent")
    out["total_files"] = int(summary.get("total_steps") or 0)
    out["processed_files"] = int(summary.get("terminal_steps") or 0)
    out["completed_files"] = int(summary.get("completed_child_steps") or 0)
    out["failed_files"] = int(summary.get("failed_child_steps") or 0)
    out["skipped_files"] = int(summary.get("partial_child_steps") or 0)
    out["deleted_files"] = int(summary.get("cancelled_child_steps") or 0)
    return out


__all__ = [
    "canonical_child_by_step",
    "compute_pipeline_summary_dict",
    "overlay_pipeline_counters_on_job_dict",
    "pipeline_steps_from_job_params",
]
