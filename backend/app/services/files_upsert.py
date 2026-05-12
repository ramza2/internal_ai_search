"""Shared SQL + helpers for upserting WebDAV-discovered items into ``files``.

Owned in one place so the root sync (Step 8) and the recursive tree sync
(Step 10) agree on schema mapping, conflict handling, and
``analysis_status`` transitions. **No** content hashing / chunking /
embedding lives here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


# Inserts a new (data_source_id, remote_path) row, or refreshes the
# metadata of the existing one. ``analysis_status`` for files is reset to
# ``PENDING`` only when ``etag``/``last_modified`` actually changed; folders
# are always ``SKIPPED``. Returns ``inserted = TRUE`` for INSERTs (using
# PostgreSQL's ``xmax = 0`` trick) and ``FALSE`` for UPDATEs.
UPSERT_FILE_SQL = """
INSERT INTO files (
    id, data_source_id, remote_path, filename, extension,
    is_directory, size_bytes, etag, last_modified,
    content_hash, mime_type, analysis_status,
    last_indexed_at, created_at, updated_at
) VALUES (
    gen_random_uuid(), %s, %s, %s, %s,
    %s, %s, %s, %s,
    NULL, %s, %s::analysis_status,
    NULL, NOW(), NOW()
)
ON CONFLICT (data_source_id, remote_path) DO UPDATE SET
    filename = EXCLUDED.filename,
    extension = EXCLUDED.extension,
    is_directory = EXCLUDED.is_directory,
    size_bytes = EXCLUDED.size_bytes,
    etag = EXCLUDED.etag,
    last_modified = EXCLUDED.last_modified,
    mime_type = EXCLUDED.mime_type,
    analysis_status = CASE
        WHEN EXCLUDED.is_directory
            THEN 'SKIPPED'::analysis_status
        WHEN files.etag IS DISTINCT FROM EXCLUDED.etag
             OR files.last_modified IS DISTINCT FROM EXCLUDED.last_modified
            THEN 'PENDING'::analysis_status
        ELSE files.analysis_status
    END,
    updated_at = NOW()
RETURNING (xmax = 0) AS inserted
"""


# Bumps ``last_scan_at`` + ``last_connection_*`` after a successful sync run.
UPDATE_DATA_SOURCE_SUCCESS_SQL = """
UPDATE data_sources
SET last_scan_at = NOW(),
    last_connection_test_at = NOW(),
    last_connection_success = TRUE,
    last_connection_message = %s,
    updated_at = NOW()
WHERE id = %s
"""


def coerce_iso_to_dt(value: Any) -> datetime | None:
    """Parse listing-layer ISO-8601 strings; non-strings / non-ISO → ``None``."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def truncate_message(msg: str, *, limit: int = 4000) -> str:
    s = (msg or "").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 3] + "..."
