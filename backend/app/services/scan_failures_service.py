"""Best-effort logging into ``scan_failures``.

The exact column layout of ``scan_failures`` is not migrated by this
repository; the helper assumes the conventional shape
``(id, scan_job_id, data_source_id, file_id, remote_path, error_code,
error_message, created_at)`` and tolerates schema/enum mismatches the
same way :mod:`app.services.scan_jobs_service` does. A failure here is
**never** allowed to break the orchestrator.

Step 12 records:

- ``DOWNLOAD_FAILED``
- ``DECODING_FAILED``
- ``FILE_TOO_LARGE``
- ``BINARY_CONTENT_DETECTED``

``UNSUPPORTED_EXTENSION`` is intentionally **not** persisted here: a
single PDF-heavy share would otherwise drown the table.

Document processing (``process-pending-documents``) additionally records:

- ``PARSING_FAILED``
- ``PASSWORD_PROTECTED``
- ``NO_EXTRACTABLE_TEXT``

Chunking (``chunk-completed-text``) may record:

- ``CHUNK_SAVE_FAILED`` — DB/chunk insert failures (persisted when the DB allows this ``error_code`` value; if ``scan_failures.error_code`` is a PostgreSQL enum that does not yet list ``CHUNK_SAVE_FAILED``, the insert is skipped safely — add the enum label via migration).
"""

from __future__ import annotations

from uuid import UUID

import psycopg

from app.db.database import get_db_connection


_INSERT_SQL = """
    INSERT INTO scan_failures (
        id,
        scan_job_id,
        data_source_id,
        file_id,
        remote_path,
        error_code,
        error_message,
        created_at
    ) VALUES (
        gen_random_uuid(),
        %s, %s, %s, %s, %s, %s,
        NOW()
    )
"""


_PERSISTABLE_ERROR_CODES: frozenset[str] = frozenset(
    {
        "DOWNLOAD_FAILED",
        "DECODING_FAILED",
        "FILE_TOO_LARGE",
        "BINARY_CONTENT_DETECTED",
        "PARSING_FAILED",
        "PASSWORD_PROTECTED",
        "NO_EXTRACTABLE_TEXT",
        "CHUNK_SAVE_FAILED",
    }
)


def _short(msg: str | None, *, limit: int = 2000) -> str | None:
    if msg is None:
        return None
    s = str(msg).strip()
    if not s:
        return None
    if len(s) <= limit:
        return s
    return s[: limit - 3] + "..."


def record_scan_failure(
    *,
    scan_job_id: UUID | None,
    data_source_id: UUID,
    file_id: UUID,
    remote_path: str | None,
    error_code: str,
    error_message: str | None,
) -> None:
    """Insert one row into ``scan_failures``. Swallows every error.

    No-op for ``error_code`` outside ``_PERSISTABLE_ERROR_CODES`` so the
    caller can safely funnel every skip/failure event through here.
    """
    code = (error_code or "").strip().upper()
    if code not in _PERSISTABLE_ERROR_CODES:
        return
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _INSERT_SQL,
                    (
                        scan_job_id,
                        data_source_id,
                        file_id,
                        remote_path,
                        code,
                        _short(error_message),
                    ),
                )
            conn.commit()
    except psycopg.errors.InvalidTextRepresentation:
        # e.g. error_code enum missing CHUNK_SAVE_FAILED — see migration TODO in module docstring
        return
    except Exception:
        # Best-effort. ``scan_failures`` may not exist yet, or the column
        # set may not match this schema assumption; either way the main
        # processing run must keep going.
        return
