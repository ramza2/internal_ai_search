"""WebDAV recursive (BFS, Depth:1) sync — upsert ``files`` only.

This service is the Step-10 entry point invoked by the
``POST /api/data-sources/{id}/sync-tree`` route. It:

1. Loads the data source row + decrypts the credential (server-side only).
2. Loads the exclusion filter from ``exclusion_policies`` (best-effort).
3. Walks the WebDAV tree via :mod:`app.webdav.recursive_listing` (BFS),
   bounded by ``max_depth`` and ``max_items``.
4. Upserts the collected items into ``files`` inside a single transaction
   together with the ``data_sources.last_scan_at`` finalization.
5. Records start / complete / fail / partial state into ``scan_jobs``
   (best-effort).

Security: ``credential_secret`` / ``credential_secret_enc`` / Authorization
headers are **never** included in responses, ``scan_jobs.error_message``,
or ``data_sources.last_connection_message``. Failure summaries are
intentionally short HTTP-status-style strings.

This stage does **not** download file bodies, hash content, chunk, embed,
or write ``document_chunks`` — those move to subsequent steps. It also
does not detect deletions: rows missing from the current traversal are
left untouched.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from app.core.config import Settings
from app.core.security import decrypt_credential_token
from app.db.database import get_db_connection
from app.schemas.data_source import WEBDAV_KINDS, SourceType
from app.services import data_source_service as datasource_svc
from app.services import scan_jobs_service
from app.services.exclusion_policy_service import load_exclusion_filter
from app.services.files_upsert import (
    UPDATE_DATA_SOURCE_SUCCESS_SQL,
    UPSERT_FILE_SQL,
    coerce_iso_to_dt,
    truncate_message,
)
from app.webdav.recursive_listing import collect_tree


SUCCESS_MESSAGE = "WebDAV recursive sync succeeded"
SUCCESS_TRUNCATED_MESSAGE = "WebDAV recursive sync stopped by max_items limit"
PARTIAL_SUCCESS_MESSAGE = (
    "WebDAV recursive sync completed with some failed directories"
)
DB_SAVE_FAIL_MESSAGE = "Failed to save WebDAV tree items to database"

# Defensive bounds on the request parameters (the route also constrains
# these via FastAPI ``Query``; keep them in sync with the spec).
MAX_DEPTH_CEILING = 20
MAX_ITEMS_CEILING = 50_000
_FAILED_PATHS_LIMIT = 20
_WARNINGS_LIMIT = 20


def _clamp(value: int, lo: int, hi: int) -> int:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _canonical_start_path(raw: str) -> str:
    s = (raw or "/").strip() or "/"
    if not s.startswith("/"):
        s = "/" + s
    if s != "/" and s.endswith("/"):
        s = s.rstrip("/") or "/"
    return s


def _record_outcome_on_data_source(ds_id: UUID, success: bool, msg: str) -> None:
    datasource_svc.update_last_connection_test_result(
        ds_id=ds_id, success=success, message=msg
    )


def _error_payload(
    *,
    base: dict[str, Any],
    scan_job_id: UUID | None,
    request_summary: dict[str, Any],
    message: str,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": "error",
        **base,
        "scan_job_id": str(scan_job_id) if scan_job_id else None,
        **request_summary,
        "message": message,
    }
    if extra:
        out.update(extra)
    if error:
        out["error"] = error
    return out


def _summarize_failed_paths(failed_paths: list[dict[str, str]]) -> str:
    if not failed_paths:
        return ""
    parts: list[str] = []
    for fp in failed_paths[:3]:
        rp = fp.get("remote_path") or "?"
        err = fp.get("error") or ""
        if err:
            parts.append(f"{rp} ({err})")
        else:
            parts.append(rp)
    head = "; ".join(parts)
    if len(failed_paths) > 3:
        head += f"; … +{len(failed_paths) - 3} more"
    return head


def run_webdav_recursive_sync(
    settings: Settings,
    ds_id: UUID,
    *,
    start_path: str,
    max_depth: int,
    max_items: int,
    include_hidden: bool,
    apply_exclusions: bool,
) -> tuple[dict[str, Any], int]:
    """Run a bounded recursive BFS sync; return ``(payload, http_status_code)``.

    Raises ``DataSourceNotFound`` when ``ds_id`` does not exist (the route
    layer maps this to HTTP 404). Other failures are returned inline.
    """
    row = datasource_svc.fetch_data_source_row_internal(ds_id=ds_id)
    source_type_str = str(row["source_type"]).strip().upper()
    base: dict[str, Any] = {
        "data_source_id": str(row["id"]),
        "name": row["name"],
        "source_type": source_type_str,
    }
    scan_job_id = scan_jobs_service.create_scan_job(ds_id=ds_id)

    md = _clamp(int(max_depth), 0, MAX_DEPTH_CEILING)
    mi = _clamp(int(max_items), 1, MAX_ITEMS_CEILING)
    sp = _canonical_start_path(start_path)
    request_summary: dict[str, Any] = {
        "start_path": sp,
        "max_depth": md,
        "max_items": mi,
    }

    try:
        source_type_enum = SourceType(source_type_str)
    except ValueError:
        source_type_enum = None
    if source_type_enum == SourceType.LOCAL_FOLDER:
        msg = "LOCAL_FOLDER recursive sync is not supported yet"
        _record_outcome_on_data_source(ds_id, False, msg)
        scan_jobs_service.fail_scan_job(job_id=scan_job_id, error_message=msg)
        return (
            _error_payload(
                base=base,
                scan_job_id=scan_job_id,
                request_summary=request_summary,
                message=msg,
            ),
            400,
        )
    if source_type_enum is None or source_type_enum not in WEBDAV_KINDS:
        msg = (
            f"Unsupported source_type {source_type_str} for recursive sync"
        )
        _record_outcome_on_data_source(ds_id, False, msg)
        scan_jobs_service.fail_scan_job(job_id=scan_job_id, error_message=msg)
        return (
            _error_payload(
                base=base,
                scan_job_id=scan_job_id,
                request_summary=request_summary,
                message=msg,
            ),
            400,
        )

    uname_raw = row.get("username")
    uname = (uname_raw or "").strip() if uname_raw is not None else ""
    enc_blob = row.get("credential_secret_enc")
    cred_present = (
        isinstance(enc_blob, str) and enc_blob.strip() != ""
    ) or (
        enc_blob is not None
        and not isinstance(enc_blob, str)
        and str(enc_blob).strip() != ""
    )
    if not uname or not cred_present:
        msg = "WebDAV username or credential is missing"
        _record_outcome_on_data_source(ds_id, False, msg)
        scan_jobs_service.fail_scan_job(job_id=scan_job_id, error_message=msg)
        return (
            _error_payload(
                base=base,
                scan_job_id=scan_job_id,
                request_summary=request_summary,
                message=msg,
            ),
            400,
        )

    try:
        password = decrypt_credential_token(settings, str(enc_blob).strip())
    except ValueError:
        msg = "Failed to decrypt stored credential"
        _record_outcome_on_data_source(ds_id, False, msg)
        scan_jobs_service.fail_scan_job(job_id=scan_job_id, error_message=msg)
        return (
            _error_payload(
                base=base,
                scan_job_id=scan_job_id,
                request_summary=request_summary,
                message=msg,
            ),
            400,
        )

    server_url = (row["server_url"] or "").strip()
    if not (
        server_url.startswith("http://") or server_url.startswith("https://")
    ):
        msg = "server_url must start with http:// or https://"
        _record_outcome_on_data_source(ds_id, False, msg)
        scan_jobs_service.fail_scan_job(job_id=scan_job_id, error_message=msg)
        return (
            _error_payload(
                base=base,
                scan_job_id=scan_job_id,
                request_summary=request_summary,
                message=msg,
            ),
            400,
        )

    wr_row = row.get("webdav_root_path")
    webdav_root = (
        wr_row.strip() if isinstance(wr_row, str) else str(wr_row or "").strip()
    )
    if not webdav_root:
        msg = "webdav_root_path is required for WebDAV-based data sources"
        _record_outcome_on_data_source(ds_id, False, msg)
        scan_jobs_service.fail_scan_job(job_id=scan_job_id, error_message=msg)
        return (
            _error_payload(
                base=base,
                scan_job_id=scan_job_id,
                request_summary=request_summary,
                message=msg,
            ),
            400,
        )

    exclusion_filter, policy_warnings = load_exclusion_filter(
        ds_id=ds_id,
        apply_exclusions=apply_exclusions,
        include_hidden=include_hidden,
    )

    items, counters, fatal = collect_tree(
        server_url=server_url,
        webdav_root_path=webdav_root,
        start_path=sp,
        max_depth=md,
        max_items=mi,
        username=uname,
        password=password,
        timeout_seconds=float(settings.webdav_timeout_seconds),
        exclusion=exclusion_filter,
    )

    aggregated_warnings: list[str] = []
    for w in policy_warnings:
        if len(aggregated_warnings) < _WARNINGS_LIMIT:
            aggregated_warnings.append(w)
    for w in counters.warnings:
        if len(aggregated_warnings) < _WARNINGS_LIMIT:
            aggregated_warnings.append(w)
    if counters.truncated and len(aggregated_warnings) < _WARNINGS_LIMIT:
        aggregated_warnings.append(f"Result was truncated by max_items={mi}")

    if fatal is not None:
        outer_msg = str(fatal.get("message") or "WebDAV recursive sync failed")
        outer_err = fatal.get("error")
        _record_outcome_on_data_source(ds_id, False, outer_msg)
        scan_jobs_service.fail_scan_job(
            job_id=scan_job_id, error_message=outer_msg
        )
        extra: dict[str, Any] = {
            "visited_directories": counters.visited_directories,
            "http_status": fatal.get("http_status"),
            "response_ms": fatal.get("response_ms"),
        }
        if aggregated_warnings:
            extra["warnings"] = aggregated_warnings
        return (
            _error_payload(
                base=base,
                scan_job_id=scan_job_id,
                request_summary=request_summary,
                message=outer_msg,
                error=str(outer_err) if outer_err else None,
                extra=extra,
            ),
            200,
        )

    inserted = 0
    updated = 0
    dirs = 0
    files_cnt = 0

    if counters.failed_count > 0:
        final_msg = PARTIAL_SUCCESS_MESSAGE
    elif counters.truncated:
        final_msg = SUCCESS_TRUNCATED_MESSAGE
    else:
        final_msg = SUCCESS_MESSAGE

    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            try:
                with conn.cursor() as cur:
                    for it in items:
                        is_dir = bool(it.get("is_directory"))
                        new_status = "SKIPPED" if is_dir else "PENDING"
                        cur.execute(
                            UPSERT_FILE_SQL,
                            (
                                ds_id,
                                it.get("remote_path"),
                                it.get("name"),
                                it.get("extension"),
                                is_dir,
                                it.get("size_bytes"),
                                it.get("etag"),
                                coerce_iso_to_dt(it.get("last_modified")),
                                it.get("content_type"),
                                new_status,
                            ),
                        )
                        res = cur.fetchone()
                        if res and res.get("inserted"):
                            inserted += 1
                        else:
                            updated += 1
                        if is_dir:
                            dirs += 1
                        else:
                            files_cnt += 1
                    cur.execute(
                        UPDATE_DATA_SOURCE_SUCCESS_SQL,
                        (truncate_message(final_msg), ds_id),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    except Exception as exc:
        scan_jobs_service.fail_scan_job(
            job_id=scan_job_id, error_message=DB_SAVE_FAIL_MESSAGE
        )
        _record_outcome_on_data_source(ds_id, False, DB_SAVE_FAIL_MESSAGE)
        return (
            _error_payload(
                base=base,
                scan_job_id=scan_job_id,
                request_summary=request_summary,
                message=DB_SAVE_FAIL_MESSAGE,
                error=str(exc),
                extra={
                    "visited_directories": counters.visited_directories,
                    "warnings": aggregated_warnings,
                },
            ),
            500,
        )

    processed = inserted + updated
    partial = counters.failed_count > 0
    status_str = "partial" if partial else "ok"

    scan_jobs_error_summary: str | None = None
    if partial:
        scan_jobs_error_summary = (
            f"{counters.failed_count} folder(s) failed during recursive sync"
        )
        details = _summarize_failed_paths(counters.failed_paths)
        if details:
            scan_jobs_error_summary += ": " + details

    scan_jobs_service.complete_scan_job(
        job_id=scan_job_id,
        total_files=counters.total_remote_items,
        processed_files=processed,
        completed_files=processed,
        failed_files=counters.failed_count,
        skipped_files=counters.excluded_count + dirs,
        error_message=scan_jobs_error_summary,
    )

    response: dict[str, Any] = {
        "status": status_str,
        **base,
        "scan_job_id": str(scan_job_id) if scan_job_id else None,
        **request_summary,
        "visited_directories": counters.visited_directories,
        "total_remote_items": counters.total_remote_items,
        "processed_items": processed,
        "inserted_count": inserted,
        "updated_count": updated,
        "directories_count": dirs,
        "files_count": files_cnt,
        "excluded_count": counters.excluded_count,
        "failed_count": counters.failed_count,
        "truncated": counters.truncated,
        "message": final_msg,
        "warnings": aggregated_warnings,
    }
    if counters.failed_paths:
        response["failed_paths"] = counters.failed_paths[:_FAILED_PATHS_LIMIT]
    return response, 200
