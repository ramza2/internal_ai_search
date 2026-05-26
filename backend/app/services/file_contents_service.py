"""DB operations for ``file_contents`` + ``files`` analysis-status transitions.

This module is the only place Step 12 talks to the database. It keeps the
SQL in one spot so the orchestrator can stay focused on classification
and download orchestration.

Transactional design:

- Each operation opens a short transaction on the provided connection
  (one connection is reused across the whole batch by the caller).
- The orchestrator ``commit()``s after each file's state transition so
  one failing file never rolls back the whole batch.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from app.db.database import get_db_connection


_FETCH_PENDING_BASE_SQL = """
    SELECT
        id,
        remote_path,
        filename,
        extension,
        size_bytes,
        content_hash
    FROM files
    WHERE data_source_id = %s
      AND is_directory = FALSE
      AND analysis_status = 'PENDING'::analysis_status
      AND analysis_status <> 'DELETED'::analysis_status
      AND remote_path IS NOT NULL
"""

_FETCH_PENDING_EXT_FILTER = (
    " AND lower(nullif(trim(extension), '')) = ANY(%s)"
)

_FETCH_PENDING_TAIL = """
    ORDER BY updated_at ASC NULLS FIRST, remote_path ASC
    LIMIT %s
"""

_FETCH_PENDING_DOCUMENTS_SQL = """
    SELECT
        id,
        remote_path,
        filename,
        extension,
        size_bytes,
        content_hash,
        analysis_status::text AS analysis_status,
        analysis_error_code
    FROM files
    WHERE data_source_id = %s
      AND is_directory = FALSE
      AND remote_path IS NOT NULL
      AND analysis_status IS DISTINCT FROM 'DELETED'::analysis_status
      AND lower(nullif(trim(extension), '')) = ANY(%s)
      AND (
            analysis_status = 'PENDING'::analysis_status
         OR (
             %s
             AND analysis_status = 'SKIPPED'::analysis_status
             AND analysis_error_code = 'UNSUPPORTED_EXTENSION'
         )
         OR (
             %s
             AND lower(nullif(trim(extension), '')) = 'hwp'
             AND analysis_status = 'SKIPPED'::analysis_status
             AND analysis_error_code = 'NO_EXTRACTABLE_TEXT'
         )
      )
    ORDER BY updated_at ASC NULLS FIRST, remote_path ASC
    LIMIT %s
"""

_FETCH_ONLY_HWP_NO_EXTRACTABLE_TEXT_SQL = """
    SELECT
        id,
        remote_path,
        filename,
        extension,
        size_bytes,
        content_hash,
        analysis_status::text AS analysis_status,
        analysis_error_code
    FROM files
    WHERE data_source_id = %s
      AND is_directory = FALSE
      AND remote_path IS NOT NULL
      AND analysis_status IS DISTINCT FROM 'DELETED'::analysis_status
      AND lower(nullif(trim(extension), '')) = 'hwp'
      AND analysis_status = 'SKIPPED'::analysis_status
      AND analysis_error_code = 'NO_EXTRACTABLE_TEXT'
    ORDER BY updated_at ASC NULLS FIRST, remote_path ASC
    LIMIT %s
"""


UPSERT_FILE_CONTENT_SQL = """
INSERT INTO file_contents (
    id,
    file_id,
    data_source_id,
    extracted_text,
    text_length,
    parser_name,
    parser_version,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    %s, %s,
    %s, %s,
    %s, %s,
    NOW(), NOW()
)
ON CONFLICT (file_id) DO UPDATE SET
    data_source_id = EXCLUDED.data_source_id,
    extracted_text = EXCLUDED.extracted_text,
    text_length = EXCLUDED.text_length,
    parser_name = EXCLUDED.parser_name,
    parser_version = EXCLUDED.parser_version,
    updated_at = NOW()
"""


UPDATE_FILE_COMPLETED_SQL = """
UPDATE files
SET analysis_status = 'COMPLETED'::analysis_status,
    analysis_error_code = NULL,
    analysis_error_message = NULL,
    content_hash = %s,
    updated_at = NOW()
WHERE id = %s
"""


UPDATE_FILE_SKIPPED_SQL = """
UPDATE files
SET analysis_status = 'SKIPPED'::analysis_status,
    analysis_error_code = %s,
    analysis_error_message = %s,
    updated_at = NOW()
WHERE id = %s
"""


UPDATE_FILE_FAILED_SQL = """
UPDATE files
SET analysis_status = 'FAILED'::analysis_status,
    analysis_error_code = %s,
    analysis_error_message = %s,
    updated_at = NOW()
WHERE id = %s
"""


_ERROR_MESSAGE_LIMIT = 2000


def truncate_error_message(value: str | None) -> str | None:
    """Trim long error blurbs to a safe size for column storage."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if len(s) <= _ERROR_MESSAGE_LIMIT:
        return s
    return s[: _ERROR_MESSAGE_LIMIT - 3] + "..."


def fetch_pending_files(
    *,
    ds_id: UUID,
    limit: int,
    include_extensions: frozenset[str] | None,
) -> list[dict[str, Any]]:
    """Return the ordered PENDING file rows for this data source.

    Folders are excluded; DELETED rows are explicitly filtered out (even
    though ``PENDING`` already excludes them — defense in depth).
    """
    params: list[Any] = [ds_id]
    sql = _FETCH_PENDING_BASE_SQL
    if include_extensions:
        sql += _FETCH_PENDING_EXT_FILTER
        params.append(sorted(include_extensions))
    sql += _FETCH_PENDING_TAIL
    params.append(int(limit))

    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def fetch_pending_document_files(
    *,
    ds_id: UUID,
    limit: int,
    document_extensions: frozenset[str],
    reprocess_skipped: bool,
    reprocess_hwp_no_extractable_text: bool = False,
    only_reprocess_hwp_no_extractable_text: bool = False,
) -> list[dict[str, Any]]:
    """Return PENDING (and optionally SKIPPED reprocess) document rows.

    ``document_extensions`` must be a non-empty normalized lowercase set
    (typically ``supported_document_extensions()`` intersected with the
    caller's ``include_extensions`` filter).

    When ``only_reprocess_hwp_no_extractable_text`` is true, **only** ``hwp``
    rows with ``SKIPPED`` / ``NO_EXTRACTABLE_TEXT`` are returned (no PENDING).

    When ``reprocess_hwp_no_extractable_text`` is true (and not only mode),
    those rows are OR'd with PENDING / other reprocess branches.
    """
    if only_reprocess_hwp_no_extractable_text:
        if not document_extensions or "hwp" not in document_extensions:
            return []
        params: list[Any] = [ds_id, int(limit)]
        sql = _FETCH_ONLY_HWP_NO_EXTRACTABLE_TEXT_SQL
    else:
        if not document_extensions:
            return []
        exts = sorted(document_extensions)
        params = [
            ds_id,
            exts,
            bool(reprocess_skipped),
            bool(reprocess_hwp_no_extractable_text),
            int(limit),
        ]
        sql = _FETCH_PENDING_DOCUMENTS_SQL
    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def apply_completed(
    conn,
    *,
    file_id: UUID,
    data_source_id: UUID,
    extracted_text: str,
    content_hash: str,
    parser_name: str,
    parser_version: str,
) -> None:
    """Upsert ``file_contents`` and flip ``files`` to ``COMPLETED``.

    Caller-owned transaction: this function neither commits nor rolls
    back. The orchestrator commits on success and rolls back per-file on
    DB failure so the batch can keep moving.
    """
    text_length = len(extracted_text or "")
    with conn.cursor() as cur:
        cur.execute(
            UPSERT_FILE_CONTENT_SQL,
            (
                file_id,
                data_source_id,
                extracted_text,
                text_length,
                parser_name,
                parser_version,
            ),
        )
        cur.execute(
            UPDATE_FILE_COMPLETED_SQL,
            (content_hash, file_id),
        )


def apply_skipped(
    conn,
    *,
    file_id: UUID,
    error_code: str,
    error_message: str | None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            UPDATE_FILE_SKIPPED_SQL,
            (
                error_code,
                truncate_error_message(error_message),
                file_id,
            ),
        )


def apply_failed(
    conn,
    *,
    file_id: UUID,
    error_code: str,
    error_message: str | None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            UPDATE_FILE_FAILED_SQL,
            (
                error_code,
                truncate_error_message(error_message),
                file_id,
            ),
        )
