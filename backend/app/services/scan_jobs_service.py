"""Best-effort persistence for ``scan_jobs`` (per-pipeline job history).

Writes are tolerant of a missing ``scan_jobs`` table or absent enum types so
the core sync flow can run even before the migration is applied. Failures here
are swallowed deliberately and never block the calling request.

Granular ``job_type`` values require migration ``021_scan_job_type_values.sql``
on the database; otherwise ``create_scan_job`` may return ``None`` while the
caller continues.

Worker-oriented helpers (``enqueue_scan_job``, ``update_scan_job_progress``,
``is_cancel_requested``) require migration ``022_scan_jobs_worker_fields.sql``.
Until then they no-op or return ``None`` / ``False``. **Do not** store
credentials, tokens, file bodies, or LLM prompts in ``job_params``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.db.database import get_db_connection

_JOB_PARAMS_BLOCKED_KEYS = frozenset(
    {
        "password",
        "current_password",
        "new_password",
        "password_hash",
        "credential_secret",
        "credential_secret_enc",
        "credential",
        "authorization",
        "access_token",
        "refresh_token",
        "chunk_text",
        "extracted_text",
        "prompt",
        "messages",
        "answer",
        "body",
        "raw",
        "content",
        "file_bytes",
        "headers",
    }
)
_MAX_JOB_PARAMS_DEPTH = 8
_MAX_JOB_PARAMS_STRING = 4000


def _sanitize_job_params_obj(obj: Any, *, depth: int = 0) -> Any:
    """Remove blocked keys and truncate long strings (recursive, JSON-like)."""
    if depth > _MAX_JOB_PARAMS_DEPTH:
        return None
    if obj is None:
        return None
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in _JOB_PARAMS_BLOCKED_KEYS:
                continue
            out[str(k)] = _sanitize_job_params_obj(v, depth=depth + 1)
        return out
    if isinstance(obj, list):
        return [_sanitize_job_params_obj(x, depth=depth + 1) for x in obj[:500]]
    if isinstance(obj, str):
        s = obj.strip()
        if len(s) > _MAX_JOB_PARAMS_STRING:
            return s[: _MAX_JOB_PARAMS_STRING - 1] + "…"
        return obj
    if isinstance(obj, (int, float, bool)):
        return obj
    return str(obj)[:500]


def sanitize_job_params_for_storage(params: dict[str, Any] | None) -> dict[str, Any] | None:
    """Prepare ``job_params`` before INSERT (enqueue). Returns ``None`` if empty."""
    if not params:
        return None
    cleaned = _sanitize_job_params_obj(params)
    if not cleaned or (isinstance(cleaned, dict) and len(cleaned) == 0):
        return None
    return cleaned if isinstance(cleaned, dict) else {"value": cleaned}


def sanitize_job_params_for_response(params: Any) -> Any:
    """Strip sensitive patterns before exposing ``job_params`` in admin JSON."""
    if params is None:
        return None
    return _sanitize_job_params_obj(params)


_JOB_INSERT_EXTRA_COLS = """
            job_params,
            cancel_requested,
            worker_id,
            heartbeat_at,
            parent_job_id,
            pipeline_step,
            retry_count,
            max_retries,
            priority,"""


def enqueue_scan_job(
    *,
    ds_id: UUID,
    job_type: str,
    requested_by: UUID | None = None,
    job_params: dict[str, Any] | None = None,
    parent_job_id: UUID | None = None,
    pipeline_step: str | None = None,
    priority: int = 0,
    max_retries: int = 1,
) -> UUID | None:
    """Insert a ``PENDING`` row for a future DB-polling worker.

    Not used by synchronous pipeline APIs yet. Returns ``None`` on any error.
    Larger ``priority`` values are dequeued first (see README).
    """
    raw = (job_type or "").strip().upper() or JOB_TYPE_MANUAL_SCAN
    if raw not in _KNOWN_JOB_TYPES:
        raw = JOB_TYPE_MANUAL_SCAN
    mr = max(0, min(int(max_retries), 1_000_000))
    pr = int(priority)
    step = (pipeline_step or "").strip()
    if len(step) > 50:
        step = step[:47] + "..."
    clean_params = sanitize_job_params_for_storage(job_params)
    stmt = f"""
        INSERT INTO scan_jobs (
            id,
            data_source_id,
            job_type,
            status,
            started_at,
            finished_at,
            requested_by,
            total_files,
            processed_files,
            completed_files,
            failed_files,
            skipped_files,
            deleted_files,
            current_file_path,
            error_message,
{_JOB_INSERT_EXTRA_COLS.strip()}
            created_at,
            updated_at
        ) VALUES (
            gen_random_uuid(),
            %s,
            %s::scan_job_type,
            'PENDING'::scan_job_status,
            NULL,
            NULL,
            %s,
            0,
            0,
            0,
            0,
            0,
            0,
            NULL,
            NULL,
            %s::jsonb,
            FALSE,
            NULL,
            NULL,
            %s,
            %s,
            0,
            %s,
            %s,
            NOW(),
            NOW()
        )
        RETURNING id
    """
    try:
        json_payload = Json(clean_params) if clean_params is not None else None
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(
                    stmt,
                    (
                        ds_id,
                        raw,
                        requested_by,
                        json_payload,
                        parent_job_id,
                        step or None,
                        mr,
                        pr,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return row["id"] if row else None
    except Exception:
        return None


def update_scan_job_progress(
    *,
    job_id: UUID,
    processed_files: int | None = None,
    completed_files: int | None = None,
    failed_files: int | None = None,
    skipped_files: int | None = None,
    deleted_files: int | None = None,
    current_file_path: str | None = None,
    heartbeat: bool = True,
) -> None:
    """Partial UPDATE for worker progress; swallow errors."""
    sets: list[str] = ["updated_at = NOW()"]
    vals: list[Any] = []

    def _add_int(col: str, v: int | None) -> None:
        nonlocal vals
        if v is not None:
            sets.append(f"{col} = %s")
            vals.append(int(v))

    _add_int("processed_files", processed_files)
    _add_int("completed_files", completed_files)
    _add_int("failed_files", failed_files)
    _add_int("skipped_files", skipped_files)
    _add_int("deleted_files", deleted_files)

    if current_file_path is not None:
        cp = str(current_file_path).strip()
        if len(cp) > 4000:
            cp = cp[:3997] + "..."
        sets.append("current_file_path = %s")
        vals.append(cp or None)

    if heartbeat:
        sets.append("heartbeat_at = NOW()")

    if len(sets) <= 1 and not heartbeat:
        return

    vals.append(job_id)
    sql = f"UPDATE scan_jobs SET {', '.join(sets)} WHERE id = %s"
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, vals)
            conn.commit()
    except Exception:
        pass


def is_cancel_requested(job_id: UUID) -> bool:
    """Return ``cancel_requested`` for ``job_id``; ``False`` on any error."""
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT cancel_requested FROM scan_jobs WHERE id = %s",
                    (job_id,),
                )
                row = cur.fetchone()
        if not row:
            return False
        return bool(row.get("cancel_requested"))
    except Exception:
        return False

# Labels align with ``action_logs.action_type`` for the same operations.
JOB_TYPE_MANUAL_SCAN = "MANUAL_SCAN"
JOB_TYPE_WEBDAV_SYNC_ROOT = "WEBDAV_SYNC_ROOT"
JOB_TYPE_WEBDAV_SYNC_TREE = "WEBDAV_SYNC_TREE"
JOB_TYPE_PROCESS_PENDING_TEXT = "PROCESS_PENDING_TEXT"
JOB_TYPE_PROCESS_PENDING_DOCUMENTS = "PROCESS_PENDING_DOCUMENTS"
JOB_TYPE_CHUNK_COMPLETED_TEXT = "CHUNK_COMPLETED_TEXT"
JOB_TYPE_EMBED_PENDING_CHUNKS = "EMBED_PENDING_CHUNKS"

_KNOWN_JOB_TYPES: frozenset[str] = frozenset(
    {
        JOB_TYPE_MANUAL_SCAN,
        JOB_TYPE_WEBDAV_SYNC_ROOT,
        JOB_TYPE_WEBDAV_SYNC_TREE,
        JOB_TYPE_PROCESS_PENDING_TEXT,
        JOB_TYPE_PROCESS_PENDING_DOCUMENTS,
        JOB_TYPE_CHUNK_COMPLETED_TEXT,
        JOB_TYPE_EMBED_PENDING_CHUNKS,
    }
)


def create_scan_job(
    *,
    ds_id: UUID,
    job_type: str = JOB_TYPE_MANUAL_SCAN,
    requested_by: UUID | None = None,
) -> UUID | None:
    """Insert a RUNNING row. Returns the new id, or ``None`` on any DB/enum error."""
    raw = (job_type or "").strip().upper() or JOB_TYPE_MANUAL_SCAN
    if raw not in _KNOWN_JOB_TYPES:
        raw = JOB_TYPE_MANUAL_SCAN
    stmt = """
        INSERT INTO scan_jobs (
            id, data_source_id, job_type, status, started_at,
            requested_by, total_files, created_at, updated_at
        ) VALUES (
            gen_random_uuid(), %s,
            %s::scan_job_type,
            'RUNNING'::scan_job_status,
            NOW(), %s, 0, NOW(), NOW()
        )
        RETURNING id
    """
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(stmt, (ds_id, raw, requested_by))
                row = cur.fetchone()
            conn.commit()
        return row["id"] if row else None
    except Exception:
        return None


def complete_scan_job(
    *,
    job_id: UUID | None,
    total_files: int,
    processed_files: int,
    completed_files: int,
    failed_files: int,
    skipped_files: int,
    deleted_files: int = 0,
    error_message: str | None = None,
) -> None:
    """Mark the row COMPLETED with counters. Optional ``error_message``
    is stored for partial-success runs (some folders failed but persistence
    proceeded). ``deleted_files`` carries the number of rows soft-marked
    ``DELETED`` during deleted-detection (``0`` when detection was skipped).
    No-op when ``job_id`` is ``None``."""
    if job_id is None:
        return
    err_clean: str | None = None
    if error_message is not None:
        s = (error_message or "").strip()
        if s:
            err_clean = s if len(s) <= 4000 else s[:3997] + "..."
    stmt = """
        UPDATE scan_jobs
        SET status = 'COMPLETED'::scan_job_status,
            finished_at = NOW(),
            total_files = %s,
            processed_files = %s,
            completed_files = %s,
            failed_files = %s,
            skipped_files = %s,
            deleted_files = %s,
            error_message = %s,
            current_file_path = NULL,
            updated_at = NOW()
        WHERE id = %s
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    stmt,
                    (
                        int(total_files),
                        int(processed_files),
                        int(completed_files),
                        int(failed_files),
                        int(skipped_files),
                        int(deleted_files),
                        err_clean,
                        job_id,
                    ),
                )
            conn.commit()
    except Exception:
        pass


def fail_scan_job(*, job_id: UUID | None, error_message: str) -> None:
    """Mark the row FAILED with a short summary message. No secrets here."""
    if job_id is None:
        return
    msg = (error_message or "").strip()
    if len(msg) > 4000:
        msg = msg[:3997] + "..."
    stmt = """
        UPDATE scan_jobs
        SET status = 'FAILED'::scan_job_status,
            finished_at = NOW(),
            error_message = %s,
            updated_at = NOW()
        WHERE id = %s
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(stmt, (msg, job_id))
            conn.commit()
    except Exception:
        pass


__all__ = [
    "JOB_TYPE_CHUNK_COMPLETED_TEXT",
    "JOB_TYPE_EMBED_PENDING_CHUNKS",
    "JOB_TYPE_MANUAL_SCAN",
    "JOB_TYPE_PROCESS_PENDING_DOCUMENTS",
    "JOB_TYPE_PROCESS_PENDING_TEXT",
    "JOB_TYPE_WEBDAV_SYNC_ROOT",
    "JOB_TYPE_WEBDAV_SYNC_TREE",
    "complete_scan_job",
    "create_scan_job",
    "enqueue_scan_job",
    "fail_scan_job",
    "is_cancel_requested",
    "sanitize_job_params_for_response",
    "sanitize_job_params_for_storage",
    "update_scan_job_progress",
]
