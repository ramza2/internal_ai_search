"""Soft-mark ``files`` rows that disappeared between recursive WebDAV scans.

The actual UPDATE is performed **inside the calling transaction** (the same
``cursor`` that just upserted the freshly-discovered items). Failures here
propagate so the orchestrator can roll back the entire batch and surface
``"Failed to mark deleted files"``.

Scope rules (see Step 11 spec):

- ``data_source_id`` is always pinned to the requested source.
- ``analysis_status = 'DELETED'`` rows are skipped (idempotent).
- ``start_path = '/'`` ⇒ entire data source.
- ``start_path = '/project-a'`` ⇒ ``remote_path = '/project-a'`` OR
  ``remote_path LIKE '/project-a/%' ESCAPE '!'`` (with ``%`` / ``_`` / ``!``
  in the path properly escaped). ``!`` is used instead of the default
  ``\\`` to dodge PostgreSQL's ``standard_conforming_strings`` quoting.

The set of paths that *did* appear in this scan is materialized into a
``TEMP TABLE ... ON COMMIT DROP`` via ``COPY`` so the surviving rows can be
identified with a single ``NOT EXISTS`` clause regardless of cardinality.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID


_DELETED_ERROR_MESSAGE = "File not found in latest WebDAV sync"


_LIKE_ESCAPE_CHAR = "!"


def _like_escape(s: str) -> str:
    """Escape LIKE wildcards with ``!``. Pair with ``ESCAPE '!'`` in the SQL.

    Using ``!`` (instead of the conventional ``\\``) sidesteps PostgreSQL's
    ``standard_conforming_strings`` quirks: a literal one-backslash escape
    character is awkward to express portably in a Python-side SQL string.
    """
    return (
        s.replace(_LIKE_ESCAPE_CHAR, _LIKE_ESCAPE_CHAR * 2)
        .replace("%", _LIKE_ESCAPE_CHAR + "%")
        .replace("_", _LIKE_ESCAPE_CHAR + "_")
    )


def _build_scope_clause(start_path: str) -> tuple[str, list]:
    """Return (sql_fragment, params) for the path-scope filter.

    Always starts with ``" AND "`` so it can be appended to the WHERE.
    Returns an empty fragment / empty params when ``start_path`` is the
    whole data source (``/``).
    """
    sp = (start_path or "/").strip() or "/"
    if not sp.startswith("/"):
        sp = "/" + sp
    if sp != "/" and sp.endswith("/"):
        sp = sp.rstrip("/") or "/"
    if sp == "/":
        return "", []
    like_pattern = _like_escape(sp) + "/%"
    return (
        " AND (files.remote_path = %s "
        "OR files.remote_path LIKE %s ESCAPE '!')",
        [sp, like_pattern],
    )


def mark_deleted_within_scope(
    cur,
    *,
    ds_id: UUID,
    start_path: str,
    collected_paths: Iterable[str],
) -> int:
    """Soft-mark stale rows in the current transaction. Returns the rowcount.

    The caller owns the connection/transaction (commit/rollback happens
    outside). Any DB error raises and lets the orchestrator roll back the
    whole batch (upserts + deletion + ``data_sources`` finalization).
    """
    scope_sql, scope_params = _build_scope_clause(start_path)

    cur.execute(
        """
        CREATE TEMP TABLE tmp_collected_paths (
            remote_path TEXT PRIMARY KEY
        ) ON COMMIT DROP
        """
    )

    deduped: list[str] = []
    seen: set[str] = set()
    for raw in collected_paths:
        if not raw:
            continue
        p = str(raw)
        if p in seen:
            continue
        seen.add(p)
        deduped.append(p)

    if deduped:
        # COPY is the fastest psycopg3 path for ingesting thousands of rows
        # into a TEMP table; keeps the operation inside the current tx.
        with cur.copy(
            "COPY tmp_collected_paths(remote_path) FROM STDIN"
        ) as copy:
            for path in deduped:
                copy.write_row([path])

    update_sql = (
        """
        UPDATE files
        SET analysis_status = 'DELETED'::analysis_status,
            analysis_error_code = NULL,
            analysis_error_message = %s,
            updated_at = NOW()
        WHERE data_source_id = %s
          AND analysis_status <> 'DELETED'::analysis_status
        """
        + scope_sql
        + """
          AND NOT EXISTS (
              SELECT 1 FROM tmp_collected_paths t
              WHERE t.remote_path = files.remote_path
          )
        """
    )
    params: list = [_DELETED_ERROR_MESSAGE, ds_id, *scope_params]
    cur.execute(update_sql, params)
    affected = int(cur.rowcount or 0)
    return affected
