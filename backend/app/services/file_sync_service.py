"""WebDAV root sync — upsert Depth:1 root items into ``files`` (no recursion).

This stage **never** downloads file bodies, computes hashes, chunks content, or
writes ``document_chunks``. It performs a single transactional upsert per
request and finalizes ``data_sources.last_scan_at`` only when the WebDAV fetch
and the DB writes both succeed.

Security:
- never logs / returns ``Authorization`` headers, ``credential_secret``, or
  ``credential_secret_enc``;
- delegates secret handling to ``listing.run_webdav_root_listing``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from app.core.config import Settings
from app.db.database import get_db_connection
from app.schemas.data_source import SourceType
from app.services import data_source_service as datasource_svc
from app.services import scan_jobs_service
from app.services.files_upsert import (
    UPDATE_DATA_SOURCE_SUCCESS_SQL,
    UPSERT_FILE_SQL,
    coerce_iso_to_dt,
    truncate_message,
)
from app.webdav.listing import run_webdav_root_listing


SUCCESS_MESSAGE = "WebDAV root sync succeeded"
SUCCESS_TRUNCATED_MESSAGE = "WebDAV root sync succeeded with truncated result"
DB_SAVE_FAIL_MESSAGE = "Failed to save WebDAV root items to database"

# Listing → sync message remapping for shared error paths.
_LISTING_TO_SYNC_MESSAGE: dict[str, str] = {
    "LOCAL_FOLDER listing is not supported yet": "LOCAL_FOLDER sync is not supported yet",
    "WebDAV root listing succeeded": SUCCESS_MESSAGE,
}


def _build_listing_error_payload(
    *,
    base: dict[str, Any],
    scan_job_id: UUID | None,
    listing_payload: dict[str, Any],
) -> dict[str, Any]:
    raw_msg = str(listing_payload.get("message") or "WebDAV listing failed")
    msg = _LISTING_TO_SYNC_MESSAGE.get(raw_msg, raw_msg)
    err = listing_payload.get("error")
    out: dict[str, Any] = {
        "status": "error",
        **base,
        "scan_job_id": str(scan_job_id) if scan_job_id else None,
        "message": msg,
    }
    if err:
        out["error"] = err
    return out


def run_webdav_root_sync(
    settings: Settings,
    ds_id: UUID,
    *,
    limit: int,
    include_hidden: bool,
) -> tuple[dict[str, Any], int]:
    """Fetch root items via PROPFIND Depth:1 and upsert them into ``files``.

    Raises ``DataSourceNotFound`` when the row does not exist (mapped to 404
    by the route layer). Other failure modes are returned inline as
    ``status: "error"`` JSON.
    """
    row = datasource_svc.fetch_data_source_row_internal(ds_id=ds_id)
    source_type_str = str(row["source_type"]).strip().upper()
    base: dict[str, Any] = {
        "data_source_id": str(row["id"]),
        "name": row["name"],
        "source_type": source_type_str,
    }

    scan_job_id = scan_jobs_service.create_scan_job(ds_id=ds_id)

    # Short-circuit LOCAL_FOLDER with the sync-specific message, before
    # invoking the listing path (which would still report correctly, but
    # keeps the response shape lean).
    try:
        source_type_enum = SourceType(source_type_str)
    except ValueError:
        source_type_enum = None
    if source_type_enum == SourceType.LOCAL_FOLDER:
        msg = "LOCAL_FOLDER sync is not supported yet"
        datasource_svc.update_last_connection_test_result(
            ds_id=ds_id, success=False, message=msg
        )
        scan_jobs_service.fail_scan_job(job_id=scan_job_id, error_message=msg)
        payload: dict[str, Any] = {
            "status": "error",
            **base,
            "scan_job_id": str(scan_job_id) if scan_job_id else None,
            "message": msg,
        }
        return payload, 400

    # WebDAV fetch + parse (and refreshes ``last_connection_*`` in DB).
    try:
        listing_payload, listing_code = run_webdav_root_listing(
            settings,
            ds_id,
            limit=limit,
            include_hidden=include_hidden,
        )
    except datasource_svc.DataSourceNotFound:
        scan_jobs_service.fail_scan_job(
            job_id=scan_job_id, error_message="Data source not found"
        )
        raise
    except Exception as exc:
        scan_jobs_service.fail_scan_job(
            job_id=scan_job_id, error_message=str(exc) or "WebDAV listing crashed"
        )
        raise

    base["webdav_url"] = listing_payload.get("webdav_url")
    # Listing may resolve the canonical name / type from the row; trust it.
    base["name"] = listing_payload.get("name", base["name"])
    base["source_type"] = listing_payload.get("source_type", base["source_type"])

    if listing_payload.get("status") != "ok":
        err_msg = _LISTING_TO_SYNC_MESSAGE.get(
            str(listing_payload.get("message") or ""),
            str(listing_payload.get("message") or "WebDAV listing failed"),
        )
        scan_jobs_service.fail_scan_job(
            job_id=scan_job_id, error_message=err_msg
        )
        return (
            _build_listing_error_payload(
                base=base,
                scan_job_id=scan_job_id,
                listing_payload=listing_payload,
            ),
            listing_code,
        )

    items: list[dict[str, Any]] = list(listing_payload.get("items") or [])
    total_remote = int(
        listing_payload.get("total_items", len(items))
    )
    truncated = bool(listing_payload.get("truncated", False))
    listing_warnings = list(listing_payload.get("warnings") or [])

    inserted_count = 0
    updated_count = 0
    directories_count = 0
    files_count = 0

    final_msg = SUCCESS_TRUNCATED_MESSAGE if truncated else SUCCESS_MESSAGE

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
                        was_inserted = bool(res and res.get("inserted"))
                        if was_inserted:
                            inserted_count += 1
                        else:
                            updated_count += 1
                        if is_dir:
                            directories_count += 1
                        else:
                            files_count += 1

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
        datasource_svc.update_last_connection_test_result(
            ds_id=ds_id, success=False, message=DB_SAVE_FAIL_MESSAGE
        )
        err_payload: dict[str, Any] = {
            "status": "error",
            **base,
            "scan_job_id": str(scan_job_id) if scan_job_id else None,
            "message": DB_SAVE_FAIL_MESSAGE,
            "error": str(exc),
        }
        return err_payload, 500

    processed = inserted_count + updated_count
    failed_count = 0  # whole-batch rollback on error → no partial successes

    scan_jobs_service.complete_scan_job(
        job_id=scan_job_id,
        total_files=total_remote,
        processed_files=processed,
        completed_files=processed,
        failed_files=failed_count,
        skipped_files=directories_count,
    )

    response: dict[str, Any] = {
        "status": "ok",
        **base,
        "scan_job_id": str(scan_job_id) if scan_job_id else None,
        "total_remote_items": total_remote,
        "processed_items": processed,
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "directories_count": directories_count,
        "files_count": files_count,
        "failed_count": failed_count,
        "truncated": truncated,
        "message": final_msg,
    }
    if listing_warnings:
        response["warnings"] = listing_warnings
    return response, 200
