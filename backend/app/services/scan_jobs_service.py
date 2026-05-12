"""Best-effort persistence for ``scan_jobs`` (history of MANUAL_SCAN / future jobs).

Writes are tolerant of a missing ``scan_jobs`` table or absent enum types so
the core sync flow can run even before the migration is applied. Failures here
are swallowed deliberately and never block the calling request.
"""

from __future__ import annotations

from uuid import UUID

from psycopg.rows import dict_row

from app.db.database import get_db_connection


def create_scan_job(*, ds_id: UUID) -> UUID | None:
    """Insert a RUNNING ``MANUAL_SCAN`` row. Returns the new id, or ``None``
    when the ``scan_jobs`` table / enum types are not available yet."""
    stmt = """
        INSERT INTO scan_jobs (
            id, data_source_id, job_type, status, started_at,
            requested_by, total_files, created_at, updated_at
        ) VALUES (
            gen_random_uuid(), %s,
            'MANUAL_SCAN'::scan_job_type,
            'RUNNING'::scan_job_status,
            NOW(), NULL, 0, NOW(), NOW()
        )
        RETURNING id
    """
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(stmt, (ds_id,))
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
