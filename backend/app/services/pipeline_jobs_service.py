"""Server-driven PIPELINE parent jobs: enqueue children and advance between steps."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from app.db.database import get_db_connection
from app.schemas.admin_jobs import (
    PROCESS_PENDING_DOCUMENTS_DEFAULT_EXTENSIONS,
    PROCESS_PENDING_TEXT_DEFAULT_EXTENSIONS,
)
from app.services import scan_jobs_service
from app.services.sync_tree_scope import (
    SCAN_SCOPE_FULL,
    SCAN_SCOPE_LIMITED,
    SERVER_MAX_PROCESS_FILE_BYTES,
    normalize_scan_scope,
)
from app.workers.worker_types import WorkerJob, WorkerRunResult

logger = logging.getLogger(__name__)

PIPELINE_CREATED_FOR = "server_pipeline_job"
CHILD_CREATED_FOR = "pipeline_child_job"

DEFAULT_PIPELINE_STEPS: tuple[str, ...] = (
    scan_jobs_service.JOB_TYPE_WEBDAV_SYNC_TREE,
    scan_jobs_service.JOB_TYPE_PROCESS_PENDING_TEXT,
    scan_jobs_service.JOB_TYPE_PROCESS_PENDING_DOCUMENTS,
    scan_jobs_service.JOB_TYPE_CHUNK_COMPLETED_TEXT,
    scan_jobs_service.JOB_TYPE_EMBED_PENDING_CHUNKS,
)

ALLOWED_PIPELINE_STEPS: frozenset[str] = frozenset(DEFAULT_PIPELINE_STEPS)

_STEP_PARAM_KEYS: dict[str, str] = {
    scan_jobs_service.JOB_TYPE_WEBDAV_SYNC_TREE: "sync_tree",
    scan_jobs_service.JOB_TYPE_PROCESS_PENDING_TEXT: "process_text",
    scan_jobs_service.JOB_TYPE_PROCESS_PENDING_DOCUMENTS: "process_documents",
    scan_jobs_service.JOB_TYPE_CHUNK_COMPLETED_TEXT: "chunk",
    scan_jobs_service.JOB_TYPE_EMBED_PENDING_CHUNKS: "embed",
}

_ACTIVE_CHILD = frozenset({"PENDING", "RUNNING", "CANCELLING"})
_SUCCESS_CHILD = frozenset({"COMPLETED", "PARTIAL"})
_BLOCKING_ENQUEUE_STATUSES = frozenset(_ACTIVE_CHILD | _SUCCESS_CHILD)


def pipeline_advisory_int_keys(parent_id: UUID) -> tuple[int, int]:
    """Two signed 32-bit keys for ``pg_try_advisory_lock`` / ``pg_advisory_unlock`` (session scope)."""
    b = parent_id.bytes
    k1 = int.from_bytes(b[0:4], "big", signed=False) & 0x7FFFFFFF
    k2 = int.from_bytes(b[4:8], "big", signed=False) & 0x7FFFFFFF
    if k1 == 0 and k2 == 0:
        k2 = 1
    return k1, k2


def default_pipeline_params() -> dict[str, Any]:
    return {
        "sync_tree": {
            "scan_scope": SCAN_SCOPE_FULL,
            "start_path": "/",
            "max_depth": None,
            "max_items": None,
            "include_hidden": False,
            "apply_exclusions": True,
            "detect_deleted": True,
        },
        "process_text": {
            "limit": 100,
            "max_file_size_bytes": SERVER_MAX_PROCESS_FILE_BYTES,
            "include_extensions": PROCESS_PENDING_TEXT_DEFAULT_EXTENSIONS,
        },
        "process_documents": {
            "limit": 50,
            "max_file_size_bytes": SERVER_MAX_PROCESS_FILE_BYTES,
            "include_extensions": PROCESS_PENDING_DOCUMENTS_DEFAULT_EXTENSIONS,
            "reprocess_skipped": False,
        },
        "chunk": {
            "limit": 100,
            "chunk_size": 1200,
            "chunk_overlap": 200,
            "min_chunk_size": 100,
            "reprocess": False,
            "include_extensions": None,
        },
        "embed": {
            "limit": 500,
            "batch_size": 32,
            "include_extensions": None,
            "reembed": False,
        },
    }


def normalize_pipeline_steps(raw: list[str] | None) -> tuple[list[str], str | None]:
    """Return ``(steps, error_message)``. Deduplicate while preserving order."""
    if not raw:
        return list(DEFAULT_PIPELINE_STEPS), None
    seen: set[str] = set()
    out: list[str] = []
    for s in raw:
        k = str(s or "").strip().upper()
        if not k:
            continue
        if k not in ALLOWED_PIPELINE_STEPS:
            return [], f"Unsupported pipeline step: {k}"
        if k in seen:
            continue
        seen.add(k)
        out.append(k)
    if not out:
        return list(DEFAULT_PIPELINE_STEPS), None
    return out, None


def merge_pipeline_params(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base)
    if not override:
        return merged
    for key, val in override.items():
        if key not in merged:
            merged[key] = val
            continue
        if isinstance(merged[key], dict) and isinstance(val, dict):
            m = dict(merged[key])
            m.update(val)
            merged[key] = m
        else:
            merged[key] = val
    return merged


def _clamp_int(v: Any, default: int, *, lo: int | None = None, hi: int | None = None) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = default
    if lo is not None and n < lo:
        n = lo
    if hi is not None and n > hi:
        n = hi
    return n


def build_step_job_params(
    step: str,
    merged_params: dict[str, Any],
    *,
    parent_job_id: UUID,
    step_index: int,
) -> dict[str, Any]:
    pk = _STEP_PARAM_KEYS.get(step)
    raw_step: dict[str, Any] = {}
    if pk and isinstance(merged_params.get(pk), dict):
        raw_step = dict(merged_params[pk])
    out = dict(raw_step)
    meta = {
        "created_for": CHILD_CREATED_FOR,
        "pipeline_parent_job_id": str(parent_job_id),
        "pipeline_step": step,
        "pipeline_step_index": int(step_index),
    }
    if step == scan_jobs_service.JOB_TYPE_WEBDAV_SYNC_TREE:
        scope = normalize_scan_scope(out.get("scan_scope"))
        base_st = {
            **meta,
            "scan_scope": scope,
            "start_path": str(out.get("start_path") or "/").strip() or "/",
            "include_hidden": bool(out.get("include_hidden", False)),
            "apply_exclusions": bool(out.get("apply_exclusions", True)),
            "detect_deleted": bool(out.get("detect_deleted", scope == SCAN_SCOPE_FULL)),
        }
        if scope == SCAN_SCOPE_FULL:
            return {**base_st, "max_depth": None, "max_items": None}
        md_raw = out.get("max_depth")
        mi_raw = out.get("max_items")
        return {
            **base_st,
            "max_depth": _clamp_int(md_raw, 3, lo=0, hi=20),
            "max_items": _clamp_int(mi_raw, 5000, lo=1, hi=50_000),
        }
    if step == scan_jobs_service.JOB_TYPE_PROCESS_PENDING_TEXT:
        inc = out.get("include_extensions")
        if inc is None:
            inc = PROCESS_PENDING_TEXT_DEFAULT_EXTENSIONS
        return {
            **meta,
            "limit": _clamp_int(out.get("limit"), 100, lo=1, hi=5000),
            "max_file_size_bytes": _clamp_int(
                out.get("max_file_size_bytes"),
                SERVER_MAX_PROCESS_FILE_BYTES,
                lo=1,
                hi=SERVER_MAX_PROCESS_FILE_BYTES,
            ),
            "include_extensions": str(inc) if inc is not None else PROCESS_PENDING_TEXT_DEFAULT_EXTENSIONS,
        }
    if step == scan_jobs_service.JOB_TYPE_PROCESS_PENDING_DOCUMENTS:
        inc = out.get("include_extensions")
        if inc is None:
            inc = PROCESS_PENDING_DOCUMENTS_DEFAULT_EXTENSIONS
        return {
            **meta,
            "limit": _clamp_int(out.get("limit"), 50, lo=1, hi=5000),
            "max_file_size_bytes": _clamp_int(
                out.get("max_file_size_bytes"),
                SERVER_MAX_PROCESS_FILE_BYTES,
                lo=1,
                hi=SERVER_MAX_PROCESS_FILE_BYTES,
            ),
            "include_extensions": str(inc) if inc is not None else PROCESS_PENDING_DOCUMENTS_DEFAULT_EXTENSIONS,
            "reprocess_skipped": bool(out.get("reprocess_skipped", False)),
        }
    if step == scan_jobs_service.JOB_TYPE_CHUNK_COMPLETED_TEXT:
        cs = _clamp_int(out.get("chunk_size"), 1200, lo=200, hi=10_000)
        co = _clamp_int(out.get("chunk_overlap"), 200, lo=0, hi=9999)
        if co >= cs:
            co = max(0, cs - 1)
        jp: dict[str, Any] = {
            **meta,
            "limit": _clamp_int(out.get("limit"), 100, lo=1, hi=5000),
            "chunk_size": cs,
            "chunk_overlap": co,
            "min_chunk_size": _clamp_int(out.get("min_chunk_size"), 100, lo=1, hi=10_000),
            "reprocess": bool(out.get("reprocess", False)),
        }
        if out.get("include_extensions") is not None:
            jp["include_extensions"] = str(out.get("include_extensions")).strip() or None
        return jp
    if step == scan_jobs_service.JOB_TYPE_EMBED_PENDING_CHUNKS:
        je: dict[str, Any] = {
            **meta,
            "limit": _clamp_int(out.get("limit"), 500, lo=1, hi=10_000),
            "batch_size": _clamp_int(out.get("batch_size"), 32, lo=1, hi=128),
            "reembed": bool(out.get("reembed", False)),
        }
        if out.get("include_extensions") is not None:
            je["include_extensions"] = str(out.get("include_extensions")).strip() or None
        return je
    return {**meta, **out}


def enqueue_pipeline_job(
    *,
    data_source_id: UUID,
    requested_by: UUID,
    steps: list[str],
    params: dict[str, Any] | None,
    priority: int = 0,
    max_retries: int = 1,
) -> UUID | None:
    merged_params = merge_pipeline_params(default_pipeline_params(), params)
    job_params: dict[str, Any] = {
        "created_for": PIPELINE_CREATED_FOR,
        "steps": list(steps),
        "params": merged_params,
        "current_step_index": 0,
    }
    clean = scan_jobs_service.sanitize_job_params_for_storage(job_params)
    if clean is None:
        return None
    return scan_jobs_service.enqueue_scan_job(
        ds_id=data_source_id,
        job_type=scan_jobs_service.JOB_TYPE_PIPELINE,
        requested_by=requested_by,
        job_params=clean,
        priority=int(priority),
        max_retries=max(0, min(int(max_retries), 1_000_000)),
    )


def enqueue_pipeline_child_job(
    *,
    parent_id: UUID,
    parent_data_source_id: UUID | None,
    parent_requested_by: UUID | None,
    parent_priority: int,
    parent_max_retries: int,
    step: str,
    step_index: int,
    merged_params: dict[str, Any],
) -> UUID | None:
    if parent_data_source_id is None:
        return None
    existing = fetch_blocking_child_for_enqueue(parent_id=parent_id, step=step)
    if existing and existing.get("id") is not None:
        return UUID(str(existing["id"]))
    step_params = build_step_job_params(
        step,
        merged_params,
        parent_job_id=parent_id,
        step_index=step_index,
    )
    clean = scan_jobs_service.sanitize_job_params_for_storage(step_params)
    return scan_jobs_service.enqueue_scan_job(
        ds_id=parent_data_source_id,
        job_type=step,
        requested_by=parent_requested_by,
        job_params=clean,
        parent_job_id=parent_id,
        pipeline_step=step,
        priority=int(parent_priority),
        max_retries=max(0, min(int(parent_max_retries), 1_000_000)),
    )


def fetch_canonical_child_for_step(*, parent_id: UUID, step: str) -> dict[str, Any] | None:
    """Earliest-created child for ``(parent_id, step)`` — canonical row when duplicates exist."""
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, status::text AS status, job_type::text AS job_type
                    FROM scan_jobs
                    WHERE parent_job_id = %s
                      AND job_type::text = %s
                    ORDER BY created_at ASC NULLS LAST, id ASC
                    LIMIT 1
                    """,
                    (parent_id, step),
                )
                row = cur.fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def fetch_blocking_child_for_enqueue(*, parent_id: UUID, step: str) -> dict[str, Any] | None:
    """If a blocking-status child already exists for this step, return its row (do not enqueue another)."""
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, status::text AS status, job_type::text AS job_type
                    FROM scan_jobs
                    WHERE parent_job_id = %s
                      AND job_type::text = %s
                      AND status::text = ANY(%s)
                    ORDER BY created_at ASC NULLS LAST, id ASC
                    LIMIT 1
                    """,
                    (parent_id, step, list(_BLOCKING_ENQUEUE_STATUSES)),
                )
                row = cur.fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def count_blocking_children_for_step(*, parent_id: UUID, step: str) -> int:
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)::int AS c
                    FROM scan_jobs
                    WHERE parent_job_id = %s
                      AND job_type::text = %s
                      AND status::text = ANY(%s)
                    """,
                    (parent_id, step, list(_BLOCKING_ENQUEUE_STATUSES)),
                )
                r = cur.fetchone() or {}
                return int(r.get("c") or 0)
    except Exception:
        return 0


def _warn_duplicate_blocking_children(*, parent_id: UUID, step: str) -> None:
    n = count_blocking_children_for_step(parent_id=parent_id, step=step)
    if n > 1:
        logger.warning(
            "Duplicate blocking pipeline children for parent=%s step=%s count=%s (using earliest created_at)",
            parent_id,
            step,
            n,
        )


# Backwards-compatible name (earliest canonical child; formerly DESC "latest").
fetch_latest_child_for_step = fetch_canonical_child_for_step


def cancel_active_pipeline_children(parent_job_id: UUID) -> int:
    """Cancel or mark cancelling active child rows. Returns number of rows touched."""
    touched = 0
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, status::text AS status
                    FROM scan_jobs
                    WHERE parent_job_id = %s
                      AND status::text IN ('PENDING', 'RUNNING', 'CANCELLING')
                    """,
                    (parent_job_id,),
                )
                rows = cur.fetchall() or []
    except Exception:
        logger.exception("cancel_active_pipeline_children: list failed parent=%s", parent_job_id)
        return 0

    for r in rows:
        cid = r["id"]
        st = str(r.get("status") or "").strip().upper()
        if st == "PENDING":
            scan_jobs_service.cancel_pending_job(cid, reason="Parent pipeline cancelled")
            touched += 1
        elif st == "RUNNING":
            scan_jobs_service.mark_job_cancelling(cid, reason="Parent pipeline cancel requested")
            touched += 1
        elif st == "CANCELLING":
            touched += 1
    return touched


def _parent_has_active_child(parent_id: UUID) -> bool:
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM scan_jobs
                    WHERE parent_job_id = %s
                      AND status::text IN ('PENDING', 'RUNNING', 'CANCELLING')
                    LIMIT 1
                    """,
                    (parent_id,),
                )
                return cur.fetchone() is not None
    except Exception:
        return False


def _aggregate_terminal_parent_status(*, parent_id: UUID, steps: list[str]) -> tuple[str, str | None]:
    """Return ``(COMPLETED|PARTIAL|FAILED|CANCELLED, message)`` from canonical child per step."""
    statuses: list[str] = []
    for step in steps:
        ch = fetch_latest_child_for_step(parent_id=parent_id, step=step)
        if not ch:
            return "FAILED", f"Missing child job for pipeline step {step}"
        st = str(ch.get("status") or "").strip().upper()
        if st in _ACTIVE_CHILD:
            return "FAILED", "Child job still active during finalize"
        statuses.append(st)
    if "FAILED" in statuses:
        return "FAILED", "One or more pipeline steps failed"
    if "CANCELLED" in statuses:
        return "CANCELLED", "One or more pipeline steps were cancelled"
    if "PARTIAL" in statuses:
        return "PARTIAL", "Pipeline completed with partial step result(s)"
    return "COMPLETED", "Pipeline completed successfully"


def _merged_params_from_parent_row(job_params: Any) -> dict[str, Any]:
    if not isinstance(job_params, dict):
        return merge_pipeline_params(default_pipeline_params(), None)
    nested = job_params.get("params")
    nested_dict = nested if isinstance(nested, dict) else None
    return merge_pipeline_params(default_pipeline_params(), nested_dict)


def handle_pipeline_parent_dequeued(job: WorkerJob, *, heartbeat_worker_id: str) -> WorkerRunResult:
    """Enqueue first child for ``current_step_index`` when missing; keep parent RUNNING."""
    wid = (heartbeat_worker_id or "").strip()[:100] or "local-worker-1"
    params = job.job_params if isinstance(job.job_params, dict) else {}
    steps_raw = params.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        return WorkerRunResult(
            success=False,
            message="PIPELINE job_params.steps missing or invalid",
            finalized_by_handler=False,
        )
    steps = [str(s).strip().upper() for s in steps_raw if str(s).strip()]
    if not steps:
        return WorkerRunResult(
            success=False,
            message="PIPELINE job_params.steps empty",
            finalized_by_handler=False,
        )
    idx = int(params.get("current_step_index") or 0)
    if idx < 0 or idx >= len(steps):
        scan_jobs_service.update_job_heartbeat(job.id, wid)
        return WorkerRunResult(
            success=True,
            message="PIPELINE coordinator idle (advancement will finalize)",
            finalized_by_handler=True,
        )

    step = steps[idx]
    merged = _merged_params_from_parent_row(params)

    child = fetch_latest_child_for_step(parent_id=job.id, step=step)
    if child:
        cst = str(child.get("status") or "").strip().upper()
        if cst in _ACTIVE_CHILD:
            scan_jobs_service.update_job_heartbeat(job.id, wid)
            return WorkerRunResult(
                success=True,
                message="PIPELINE waiting on active child job",
                finalized_by_handler=True,
            )
        scan_jobs_service.update_job_heartbeat(job.id, wid)
        return WorkerRunResult(
            success=True,
            message="PIPELINE child already terminal; advancement will continue",
            finalized_by_handler=True,
        )

    new_id = enqueue_pipeline_child_job(
        parent_id=job.id,
        parent_data_source_id=job.data_source_id,
        parent_requested_by=job.requested_by,
        parent_priority=job.priority,
        parent_max_retries=job.max_retries,
        step=step,
        step_index=idx,
        merged_params=merged,
    )
    if new_id is None:
        return WorkerRunResult(
            success=False,
            message="Failed to enqueue pipeline child job",
            finalized_by_handler=False,
        )
    scan_jobs_service.update_job_heartbeat(job.id, wid)
    return WorkerRunResult(
        success=True,
        message="Pipeline child job enqueued",
        finalized_by_handler=True,
    )


def _fetch_pipeline_parent_row(parent_id: UUID) -> dict[str, Any] | None:
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        id,
                        data_source_id,
                        job_type::text AS job_type,
                        status::text AS status,
                        job_params,
                        requested_by,
                        priority,
                        COALESCE(max_retries, 1) AS max_retries
                    FROM scan_jobs
                    WHERE id = %s
                      AND job_type::text = 'PIPELINE'
                    """,
                    (parent_id,),
                )
                row = cur.fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def _advance_single_pipeline_parent(parent_id: UUID, wid: str) -> None:
    """Advance one PIPELINE parent (caller must hold per-parent advisory lock)."""
    prow = _fetch_pipeline_parent_row(parent_id)
    if not prow:
        return
    pid = prow["id"]
    pst = str(prow.get("status") or "").strip().upper()

    if pst == "CANCELLING":
        cancel_active_pipeline_children(pid)
        if not _parent_has_active_child(pid):
            scan_jobs_service.mark_job_cancelled(pid, message="Pipeline cancelled")
        scan_jobs_service.update_job_heartbeat(pid, wid)
        return

    raw_params = prow.get("job_params")
    if not isinstance(raw_params, dict):
        scan_jobs_service.mark_job_failed(pid, error_message="PIPELINE job_params missing")
        return

    steps_list = raw_params.get("steps")
    if not isinstance(steps_list, list) or not steps_list:
        scan_jobs_service.mark_job_failed(pid, error_message="PIPELINE steps invalid")
        return
    steps = [str(s).strip().upper() for s in steps_list if str(s).strip()]
    merged = _merged_params_from_parent_row(raw_params)
    idx = int(raw_params.get("current_step_index") or 0)

    if idx >= len(steps):
        agg, msg = _aggregate_terminal_parent_status(parent_id=pid, steps=steps)
        if agg == "COMPLETED":
            scan_jobs_service.mark_job_completed(pid, message=msg)
        elif agg == "PARTIAL":
            scan_jobs_service.mark_job_partial(pid, message=msg)
        elif agg == "FAILED":
            scan_jobs_service.mark_job_failed(pid, error_message=msg or "Pipeline failed")
        else:
            scan_jobs_service.mark_job_cancelled(pid, message=msg or "Pipeline cancelled")
        return

    step = steps[idx]
    _warn_duplicate_blocking_children(parent_id=pid, step=step)
    child = fetch_canonical_child_for_step(parent_id=pid, step=step)
    if child is None:
        enqueue_pipeline_child_job(
            parent_id=pid,
            parent_data_source_id=prow.get("data_source_id"),
            parent_requested_by=prow.get("requested_by"),
            parent_priority=int(prow.get("priority") or 0),
            parent_max_retries=int(prow.get("max_retries") or 1),
            step=step,
            step_index=idx,
            merged_params=merged,
        )
        scan_jobs_service.update_job_heartbeat(pid, wid)
        return

    cst = str(child.get("status") or "").strip().upper()
    if cst in _ACTIVE_CHILD:
        scan_jobs_service.update_job_heartbeat(pid, wid)
        return

    if cst == "FAILED":
        scan_jobs_service.mark_job_failed(pid, error_message="Pipeline step failed")
        return
    if cst == "CANCELLED":
        scan_jobs_service.mark_job_cancelled(pid, message="Pipeline step cancelled")
        return

    if cst in _SUCCESS_CHILD:
        next_idx = idx + 1
        new_params = dict(raw_params)
        new_params["current_step_index"] = next_idx
        scan_jobs_service.update_scan_job_job_params(pid, new_params)
        if next_idx >= len(steps):
            agg, msg = _aggregate_terminal_parent_status(parent_id=pid, steps=steps)
            if agg == "COMPLETED":
                scan_jobs_service.mark_job_completed(pid, message=msg)
            elif agg == "PARTIAL":
                scan_jobs_service.mark_job_partial(pid, message=msg)
            elif agg == "FAILED":
                scan_jobs_service.mark_job_failed(pid, error_message=msg or "Pipeline failed")
            else:
                scan_jobs_service.mark_job_cancelled(pid, message=msg or "Pipeline cancelled")
        else:
            nxt = steps[next_idx]
            _warn_duplicate_blocking_children(parent_id=pid, step=nxt)
            enqueue_pipeline_child_job(
                parent_id=pid,
                parent_data_source_id=prow.get("data_source_id"),
                parent_requested_by=prow.get("requested_by"),
                parent_priority=int(prow.get("priority") or 0),
                parent_max_retries=int(prow.get("max_retries") or 1),
                step=nxt,
                step_index=next_idx,
                merged_params=merged,
            )
        scan_jobs_service.update_job_heartbeat(pid, wid)
        return

    scan_jobs_service.update_job_heartbeat(pid, wid)


def advance_running_pipeline_jobs(*, worker_id: str) -> int:
    """Drive RUNNING/CANCELLING PIPELINE parents: enqueue next child or finalize. Returns parents touched."""
    wid = (worker_id or "").strip()[:100] or "local-worker-1"
    touched = 0
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id
                    FROM scan_jobs
                    WHERE job_type::text = 'PIPELINE'
                      AND status::text IN ('RUNNING', 'CANCELLING')
                    ORDER BY created_at ASC NULLS LAST
                    """
                )
                parents = cur.fetchall() or []
    except Exception:
        logger.exception("advance_running_pipeline_jobs: list parents failed")
        return 0

    for prow in parents:
        pid = prow["id"]
        try:
            with get_db_connection() as lock_conn:
                lock_conn.autocommit = True
                k1, k2 = pipeline_advisory_int_keys(pid)
                with lock_conn.cursor() as cur:
                    cur.execute("SELECT pg_try_advisory_lock(%s::int, %s::int)", (k1, k2))
                    got = cur.fetchone()
                    locked = bool(got and got[0])
                if not locked:
                    logger.debug(
                        "advance_running_pipeline_jobs: skip parent_id=%s (another worker holds lock)",
                        pid,
                    )
                    continue
                try:
                    _advance_single_pipeline_parent(pid, wid)
                finally:
                    with lock_conn.cursor() as cur:
                        cur.execute("SELECT pg_advisory_unlock(%s::int, %s::int)", (k1, k2))
            touched += 1
        except Exception:
            logger.exception("advance_running_pipeline_jobs failed parent_id=%s", pid)
    return touched


__all__ = [
    "ALLOWED_PIPELINE_STEPS",
    "CHILD_CREATED_FOR",
    "DEFAULT_PIPELINE_STEPS",
    "PIPELINE_CREATED_FOR",
    "advance_running_pipeline_jobs",
    "build_step_job_params",
    "cancel_active_pipeline_children",
    "count_blocking_children_for_step",
    "default_pipeline_params",
    "enqueue_pipeline_child_job",
    "enqueue_pipeline_job",
    "fetch_blocking_child_for_enqueue",
    "fetch_canonical_child_for_step",
    "fetch_latest_child_for_step",
    "handle_pipeline_parent_dequeued",
    "merge_pipeline_params",
    "normalize_pipeline_steps",
    "pipeline_advisory_int_keys",
]
