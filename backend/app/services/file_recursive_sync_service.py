"""WebDAV recursive (BFS, Depth:1) sync — upsert ``files`` only.

This service is the Step-10 entry point invoked by the
``POST /api/data-sources/{id}/sync-tree`` route **and** by the DB polling
worker for ``WEBDAV_SYNC_TREE`` jobs (via :func:`run_webdav_recursive_sync_core`
with an existing ``scan_jobs`` row). It:

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
or write ``document_chunks`` — those move to subsequent steps.

Step 11 adds **opt-in deleted detection** (``detect_deleted=true``): when
all safety conditions hold (non-truncated, no failed folders, exclusions
disabled, hidden items included), rows whose ``remote_path`` falls inside
the current scope but were not seen in this walk are soft-marked
``analysis_status = 'DELETED'``. The deletion UPDATE runs inside the same
transaction as the upserts; any failure rolls back the entire batch.
"""

from __future__ import annotations

from typing import Any, Callable, NamedTuple
from uuid import UUID

from psycopg.rows import dict_row

from app.core.config import Settings
from app.core.security import decrypt_credential_token
from app.db.database import get_db_connection
from app.schemas.data_source import WEBDAV_KINDS, SourceType
from app.services import data_source_service as datasource_svc
from app.services import scan_jobs_service
from app.services.exclusion_policy_service import load_exclusion_filter
from app.services.files_deletion_service import mark_deleted_within_scope
from app.services.files_upsert import (
    UPDATE_DATA_SOURCE_SUCCESS_SQL,
    UPSERT_FILE_SQL,
    coerce_iso_to_dt,
    truncate_message,
)
from app.services.sync_tree_scope import (
    SYNC_FULL_BLOCKED_MESSAGE,
    emergency_max_items_from_settings,
    normalize_scan_scope,
    resolve_sync_tree_limits,
)
from app.webdav.recursive_listing import collect_tree


SUCCESS_MESSAGE = "WebDAV recursive sync succeeded"
SUCCESS_TRUNCATED_MESSAGE = "WebDAV recursive sync stopped by max_items limit"
PARTIAL_SUCCESS_MESSAGE = (
    "WebDAV recursive sync completed with some failed directories"
)
DB_SAVE_FAIL_MESSAGE = "Failed to save WebDAV tree items to database"
DELETION_MARK_FAIL_MESSAGE = "Failed to mark deleted files"


# Deleted-detection skip warnings — surfaced in the response's ``warnings``
# list. Multiple reasons can co-exist (e.g. partial + exclusions).
_WARN_DETECT_DISABLED = (
    "Deleted detection is disabled. "
    "Existing files not found in this sync were not marked as DELETED."
)
_WARN_SKIP_TRUNCATED = (
    "Deleted detection was skipped because sync result was truncated."
)
_WARN_SKIP_PARTIAL = (
    "Deleted detection was skipped because some directories failed to sync."
)
_WARN_SKIP_EXCLUSIONS = (
    "Deleted detection was skipped because exclusion policies were applied. "
    "Run with apply_exclusions=false for deleted detection."
)
_WARN_SKIP_HIDDEN = (
    "Deleted detection was skipped because hidden items were excluded."
)

# LIMITED-mode bounds (sync HTTP Query and worker LIMITED jobs).
MAX_DEPTH_CEILING = 20
MAX_ITEMS_CEILING = 50_000
_FAILED_PATHS_LIMIT = 20
_WARNINGS_LIMIT = 20
_PROGRESS_HEARTBEAT_EVERY = 100


class RecursiveSyncCoreOutcome(NamedTuple):
    """Result of :func:`run_webdav_recursive_sync_core` (HTTP payload + status)."""

    payload: dict[str, Any]
    http_status: int
    finalized_scan_job: bool


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


def _decide_deleted_detection(
    *,
    detect_deleted: bool,
    truncated: bool,
    failed_count: int,
    apply_exclusions: bool,
    include_hidden: bool,
) -> tuple[bool, list[str]]:
    """Return ``(should_run, skip_warnings)`` for the deletion stage.

    All skip reasons are aggregated so the operator gets a clear picture of
    what blocked detection. When ``detect_deleted`` is ``False`` we surface
    the single "disabled" notice rather than the gate-specific warnings.
    """
    if not detect_deleted:
        return False, [_WARN_DETECT_DISABLED]

    skips: list[str] = []
    if truncated:
        skips.append(_WARN_SKIP_TRUNCATED)
    if failed_count > 0:
        skips.append(_WARN_SKIP_PARTIAL)
    if apply_exclusions:
        skips.append(_WARN_SKIP_EXCLUSIONS)
    if not include_hidden:
        skips.append(_WARN_SKIP_HIDDEN)
    return (not skips), skips


def _maybe_worker_heartbeat(
    scan_job_id: UUID | None,
    *,
    heartbeat_worker_id: str | None,
    processed: int,
    current_path: str | None,
) -> None:
    """Best-effort progress + heartbeat for long worker runs.

    Fine-grained per-folder heartbeats can be added later; see README.
    """
    if not scan_job_id:
        return
    if heartbeat_worker_id:
        scan_jobs_service.update_job_heartbeat(scan_job_id, heartbeat_worker_id)
    scan_jobs_service.update_scan_job_progress(
        job_id=scan_job_id,
        processed_files=processed,
        current_file_path=current_path,
        heartbeat=True,
    )


def run_webdav_recursive_sync_core(
    settings: Settings,
    ds_id: UUID,
    *,
    scan_job_id: UUID | None,
    start_path: str,
    scan_scope: str | None = None,
    max_depth: int | None = None,
    max_items: int | None = None,
    include_hidden: bool,
    apply_exclusions: bool,
    detect_deleted: bool = False,
    requested_by: UUID | None = None,
    cancel_check: Callable[[], bool] | None = None,
    heartbeat_worker_id: str | None = None,
) -> RecursiveSyncCoreOutcome:
    """Execute recursive sync using an **existing** ``scan_jobs`` row.

    The synchronous HTTP route creates the row via ``create_scan_job`` then
    calls this core. The DB worker dequeues a ``PENDING`` row (already
    ``RUNNING``) and passes ``scan_job_id=job.id`` so no duplicate job rows are
    created.

    Finalization uses ``complete_scan_job`` / ``fail_scan_job`` /
    ``mark_job_cancelled`` — callers that delegate terminal state must set
    ``WorkerRunResult.finalized_by_handler`` and avoid double-updates.
    """
    _ = requested_by  # parity with sync entrypoint; job row carries requester
    row = datasource_svc.fetch_data_source_row_internal(ds_id=ds_id)
    source_type_str = str(row["source_type"]).strip().upper()
    base: dict[str, Any] = {
        "data_source_id": str(row["id"]),
        "name": row["name"],
        "source_type": source_type_str,
    }

    scope = normalize_scan_scope(scan_scope)
    emergency_mi = emergency_max_items_from_settings(settings)
    md, mi, is_full_scope = resolve_sync_tree_limits(
        scope,
        max_depth,
        max_items,
        emergency_max_items=emergency_mi,
    )
    sp = _canonical_start_path(start_path)
    detect_deleted_flag = bool(detect_deleted)
    request_summary: dict[str, Any] = {
        "scan_scope": scope,
        "start_path": sp,
        "max_depth": None if is_full_scope else md,
        "max_items": None if is_full_scope else mi,
    }
    if is_full_scope and emergency_mi > 0:
        request_summary["emergency_max_items"] = emergency_mi

    try:
        source_type_enum = SourceType(source_type_str)
    except ValueError:
        source_type_enum = None
    if source_type_enum == SourceType.LOCAL_FOLDER:
        msg = "LOCAL_FOLDER recursive sync is not supported yet"
        _record_outcome_on_data_source(ds_id, False, msg)
        scan_jobs_service.fail_scan_job(job_id=scan_job_id, error_message=msg)
        return RecursiveSyncCoreOutcome(
            _error_payload(
                base=base,
                scan_job_id=scan_job_id,
                request_summary=request_summary,
                message=msg,
            ),
            400,
            True,
        )
    if source_type_enum is None or source_type_enum not in WEBDAV_KINDS:
        msg = (
            f"Unsupported source_type {source_type_str} for recursive sync"
        )
        _record_outcome_on_data_source(ds_id, False, msg)
        scan_jobs_service.fail_scan_job(job_id=scan_job_id, error_message=msg)
        return RecursiveSyncCoreOutcome(
            _error_payload(
                base=base,
                scan_job_id=scan_job_id,
                request_summary=request_summary,
                message=msg,
            ),
            400,
            True,
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
        return RecursiveSyncCoreOutcome(
            _error_payload(
                base=base,
                scan_job_id=scan_job_id,
                request_summary=request_summary,
                message=msg,
            ),
            400,
            True,
        )

    try:
        password = decrypt_credential_token(settings, str(enc_blob).strip())
    except ValueError:
        msg = "Failed to decrypt stored credential"
        _record_outcome_on_data_source(ds_id, False, msg)
        scan_jobs_service.fail_scan_job(job_id=scan_job_id, error_message=msg)
        return RecursiveSyncCoreOutcome(
            _error_payload(
                base=base,
                scan_job_id=scan_job_id,
                request_summary=request_summary,
                message=msg,
            ),
            400,
            True,
        )

    server_url = (row["server_url"] or "").strip()
    if not (
        server_url.startswith("http://") or server_url.startswith("https://")
    ):
        msg = "server_url must start with http:// or https://"
        _record_outcome_on_data_source(ds_id, False, msg)
        scan_jobs_service.fail_scan_job(job_id=scan_job_id, error_message=msg)
        return RecursiveSyncCoreOutcome(
            _error_payload(
                base=base,
                scan_job_id=scan_job_id,
                request_summary=request_summary,
                message=msg,
            ),
            400,
            True,
        )

    wr_row = row.get("webdav_root_path")
    webdav_root = (
        wr_row.strip() if isinstance(wr_row, str) else str(wr_row or "").strip()
    )
    if not webdav_root:
        msg = "webdav_root_path is required for WebDAV-based data sources"
        _record_outcome_on_data_source(ds_id, False, msg)
        scan_jobs_service.fail_scan_job(job_id=scan_job_id, error_message=msg)
        return RecursiveSyncCoreOutcome(
            _error_payload(
                base=base,
                scan_job_id=scan_job_id,
                request_summary=request_summary,
                message=msg,
            ),
            400,
            True,
        )

    if scan_job_id and heartbeat_worker_id:
        scan_jobs_service.update_job_heartbeat(scan_job_id, heartbeat_worker_id)
    if cancel_check and scan_job_id and cancel_check():
        scan_jobs_service.mark_job_cancelled(
            scan_job_id, message="Job cancelled by request"
        )
        return RecursiveSyncCoreOutcome(
            _error_payload(
                base=base,
                scan_job_id=scan_job_id,
                request_summary=request_summary,
                message="Job cancelled by request",
            ),
            200,
            True,
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

    if scan_job_id:
        scan_jobs_service.update_scan_job_progress(
            job_id=scan_job_id,
            processed_files=0,
            current_file_path=sp,
            heartbeat=True,
        )
        if heartbeat_worker_id:
            scan_jobs_service.update_job_heartbeat(scan_job_id, heartbeat_worker_id)

    if cancel_check and scan_job_id and cancel_check():
        scan_jobs_service.mark_job_cancelled(
            scan_job_id, message="Job cancelled by request"
        )
        return RecursiveSyncCoreOutcome(
            _error_payload(
                base=base,
                scan_job_id=scan_job_id,
                request_summary=request_summary,
                message="Job cancelled by request",
            ),
            200,
            True,
        )

    aggregated_warnings: list[str] = []
    for w in policy_warnings:
        if len(aggregated_warnings) < _WARNINGS_LIMIT:
            aggregated_warnings.append(w)
    for w in counters.warnings:
        if len(aggregated_warnings) < _WARNINGS_LIMIT:
            aggregated_warnings.append(w)
    if counters.truncated and len(aggregated_warnings) < _WARNINGS_LIMIT:
        if is_full_scope and emergency_mi > 0:
            aggregated_warnings.append(
                f"Result was truncated by emergency max_items={emergency_mi}"
            )
        elif is_full_scope:
            aggregated_warnings.append(
                "Result was truncated during full repository scan (internal limit)"
            )
        else:
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
            "detect_deleted": detect_deleted_flag,
        }
        if aggregated_warnings:
            extra["warnings"] = aggregated_warnings
        return RecursiveSyncCoreOutcome(
            _error_payload(
                base=base,
                scan_job_id=scan_job_id,
                request_summary=request_summary,
                message=outer_msg,
                error=str(outer_err) if outer_err else None,
                extra=extra,
            ),
            200,
            True,
        )

    # Decide whether deletion detection will run *before* opening the DB
    # transaction so we can shape ``aggregated_warnings`` consistently and
    # bail out of the deletion stage cheaply on the gate failures.
    should_detect_deleted, deletion_skip_warnings = _decide_deleted_detection(
        detect_deleted=detect_deleted_flag,
        truncated=counters.truncated,
        failed_count=counters.failed_count,
        apply_exclusions=apply_exclusions,
        include_hidden=include_hidden,
    )
    for w in deletion_skip_warnings:
        if len(aggregated_warnings) < _WARNINGS_LIMIT:
            aggregated_warnings.append(w)

    collected_paths: list[str] = [
        str(it.get("remote_path"))
        for it in items
        if it.get("remote_path")
    ]

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

    deleted_marked_count = 0
    deletion_marking_failed = False

    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            cancelled = False
            try:
                with conn.cursor() as cur:
                    for idx, it in enumerate(items):
                        if cancel_check and scan_job_id and (idx == 0 or (idx + 1) % 50 == 0):
                            if cancel_check():
                                cancelled = True
                                break
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
                        proc = inserted + updated
                        if scan_job_id and (idx + 1) % _PROGRESS_HEARTBEAT_EVERY == 0:
                            _maybe_worker_heartbeat(
                                scan_job_id,
                                heartbeat_worker_id=heartbeat_worker_id,
                                processed=proc,
                                current_path=str(it.get("remote_path") or "") or None,
                            )

                    if cancelled:
                        pass
                    elif should_detect_deleted:
                        try:
                            deleted_marked_count = mark_deleted_within_scope(
                                cur,
                                ds_id=ds_id,
                                start_path=sp,
                                collected_paths=collected_paths,
                            )
                        except Exception:
                            deletion_marking_failed = True
                            raise

                    if not cancelled:
                        cur.execute(
                            UPDATE_DATA_SOURCE_SUCCESS_SQL,
                            (truncate_message(final_msg), ds_id),
                        )
                if cancelled:
                    conn.rollback()
                    if scan_job_id:
                        scan_jobs_service.mark_job_cancelled(
                            scan_job_id, message="Job cancelled by request"
                        )
                    return RecursiveSyncCoreOutcome(
                        _error_payload(
                            base=base,
                            scan_job_id=scan_job_id,
                            request_summary=request_summary,
                            message="Job cancelled by request",
                        ),
                        200,
                        True,
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    except Exception as exc:
        fail_msg = (
            DELETION_MARK_FAIL_MESSAGE
            if deletion_marking_failed
            else DB_SAVE_FAIL_MESSAGE
        )
        scan_jobs_service.fail_scan_job(
            job_id=scan_job_id, error_message=fail_msg
        )
        _record_outcome_on_data_source(ds_id, False, fail_msg)
        return RecursiveSyncCoreOutcome(
            _error_payload(
                base=base,
                scan_job_id=scan_job_id,
                request_summary=request_summary,
                message=fail_msg,
                error=str(exc),
                extra={
                    "visited_directories": counters.visited_directories,
                    "detect_deleted": detect_deleted_flag,
                    "warnings": aggregated_warnings,
                },
            ),
            500,
            True,
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

    if scan_job_id and heartbeat_worker_id:
        scan_jobs_service.update_job_heartbeat(scan_job_id, heartbeat_worker_id)

    scan_jobs_service.complete_scan_job(
        job_id=scan_job_id,
        total_files=counters.total_remote_items,
        processed_files=processed,
        completed_files=processed,
        failed_files=counters.failed_count,
        skipped_files=counters.excluded_count + dirs,
        deleted_files=deleted_marked_count,
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
        "deleted_marked_count": deleted_marked_count,
        "failed_count": counters.failed_count,
        "truncated": counters.truncated,
        "detect_deleted": detect_deleted_flag,
        "message": final_msg,
        "warnings": aggregated_warnings,
    }
    if counters.failed_paths:
        response["failed_paths"] = counters.failed_paths[:_FAILED_PATHS_LIMIT]
    return RecursiveSyncCoreOutcome(response, 200, True)


def run_webdav_recursive_sync(
    settings: Settings,
    ds_id: UUID,
    *,
    start_path: str,
    scan_scope: str | None = None,
    max_depth: int = 3,
    max_items: int = 5000,
    include_hidden: bool,
    apply_exclusions: bool,
    detect_deleted: bool = False,
    requested_by: UUID | None = None,
) -> tuple[dict[str, Any], int]:
    """Synchronous HTTP entry: create ``RUNNING`` scan job then run core logic."""
    if normalize_scan_scope(scan_scope) == "FULL":
        return (
            {
                "status": "error",
                "data_source_id": str(ds_id),
                "message": SYNC_FULL_BLOCKED_MESSAGE,
                "scan_scope": "FULL",
            },
            400,
        )
    scan_job_id = scan_jobs_service.create_scan_job(
        ds_id=ds_id,
        job_type=scan_jobs_service.JOB_TYPE_WEBDAV_SYNC_TREE,
        requested_by=requested_by,
    )
    out = run_webdav_recursive_sync_core(
        settings,
        ds_id,
        scan_job_id=scan_job_id,
        start_path=start_path,
        scan_scope=scan_scope or "LIMITED",
        max_depth=max_depth,
        max_items=max_items,
        include_hidden=include_hidden,
        apply_exclusions=apply_exclusions,
        detect_deleted=detect_deleted,
        requested_by=requested_by,
        cancel_check=None,
        heartbeat_worker_id=None,
    )
    return out.payload, out.http_status
