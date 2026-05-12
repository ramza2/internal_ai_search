"""Read ``exclusion_policies`` rows and turn them into a traversal filter.

Loading is best-effort: when the ``exclusion_policies`` table or enum types
do not exist yet, the service returns an empty filter and a warning rather
than failing the recursive sync. ``apply_exclusions=False`` short-circuits
the DB read entirely (the hidden-name filter still applies separately).
"""

from __future__ import annotations

from uuid import UUID

from psycopg.rows import dict_row

from app.db.database import get_db_connection
from app.webdav.recursive_listing import ExclusionFilter


_QUERY = """
SELECT
    policy_type::text AS policy_type,
    pattern,
    data_source_id
FROM exclusion_policies
WHERE (data_source_id IS NULL OR data_source_id = %s)
  AND COALESCE(is_active, TRUE) = TRUE
"""


def load_exclusion_filter(
    *,
    ds_id: UUID,
    apply_exclusions: bool,
    include_hidden: bool,
) -> tuple[ExclusionFilter, list[str]]:
    """Compose an ``ExclusionFilter`` from active policies for ``ds_id``.

    Always returns a filter (empty when policies cannot be loaded). The
    second tuple element is a list of warnings (empty in the happy path).
    Policy-loading exceptions never propagate to the request.
    """
    folder_names: set[str] = set()
    extensions: set[str] = set()
    path_patterns: list[str] = []
    max_file_size_bytes: int | None = None
    warnings: list[str] = []

    if apply_exclusions:
        rows: list[dict] = []
        try:
            with get_db_connection() as conn:
                conn.row_factory = dict_row
                with conn.cursor() as cur:
                    cur.execute(_QUERY, (ds_id,))
                    rows = list(cur.fetchall())
        except Exception:
            warnings.append(
                "exclusion_policies could not be loaded; running without policies"
            )
            rows = []

        for row in rows:
            pt = str(row.get("policy_type") or "").strip().upper()
            raw = row.get("pattern")
            pat = str(raw).strip() if raw is not None else ""
            if not pt or not pat:
                continue
            if pt == "FOLDER":
                folder_names.add(pat.strip("/ \t").lower())
            elif pt == "EXTENSION":
                ext = pat.lower().lstrip(".")
                if ext:
                    extensions.add(ext)
            elif pt == "PATH_PATTERN":
                path_patterns.append(pat)
            elif pt == "MAX_FILE_SIZE":
                try:
                    val = int(float(pat))
                except (TypeError, ValueError):
                    warnings.append(
                        "MAX_FILE_SIZE policy value is not a valid integer; ignored"
                    )
                    continue
                if val < 0:
                    warnings.append(
                        "MAX_FILE_SIZE policy value is negative; ignored"
                    )
                    continue
                if max_file_size_bytes is None or val < max_file_size_bytes:
                    max_file_size_bytes = val
            else:
                warnings.append(
                    f"Unknown exclusion policy_type '{pt}' was ignored"
                )

    flt = ExclusionFilter(
        folder_names=frozenset(folder_names),
        extensions=frozenset(extensions),
        path_patterns=tuple(path_patterns),
        max_file_size_bytes=max_file_size_bytes,
        apply=apply_exclusions,
        include_hidden=include_hidden,
    )
    return flt, warnings
