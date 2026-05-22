"""Service-layer E2E for one SKIPPED/NO_EXTRACTABLE_TEXT HWP (no secrets in stdout)."""
from __future__ import annotations

import json
from uuid import UUID

from app.core.config import Settings
from app.db.database import get_db_connection
from app.services.file_contents_service import fetch_pending_document_files
from app.services.pending_document_processor_service import (
    _pending_document_webdav_context,
    _planned_action_for_row,
    _process_one_file,
    run_process_pending_documents,
)
from psycopg.rows import dict_row

SKIPPED_FILE_ID = UUID("9f69bb54-b4a2-4c2e-914b-d95cc76bf3f4")
DS_ID = UUID("cd148eec-6d05-4486-b0b4-ebecebb3860a")


def _file_row(file_id: UUID) -> dict | None:
    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, remote_path, filename, extension, size_bytes, content_hash,
                       analysis_status::text AS analysis_status, analysis_error_code
                FROM files WHERE id = %s
                """,
                (file_id,),
            )
            r = cur.fetchone()
    return dict(r) if r else None


def _file_status(file_id: UUID) -> dict:
    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT f.analysis_status::text AS analysis_status,
                       f.analysis_error_code,
                       fc.parser_name,
                       fc.text_length
                FROM files f
                LEFT JOIN file_contents fc ON fc.file_id = f.id
                WHERE f.id = %s
                """,
                (file_id,),
            )
            r = cur.fetchone()
    return dict(r) if r else {}


def main() -> int:
    settings = Settings()
    out: dict = {"file_id": str(SKIPPED_FILE_ID), "data_source_id": str(DS_ID)}

    row = _file_row(SKIPPED_FILE_ID)
    if not row:
        print(json.dumps({"error": "file not found"}, indent=2))
        return 1
    out["before"] = _file_status(SKIPPED_FILE_ID)
    planned, reason = _planned_action_for_row(row)
    out["planned_action"] = planned
    out["planned_reason"] = reason

    targets = fetch_pending_document_files(
        ds_id=DS_ID,
        limit=5000,
        document_extensions=frozenset({"hwp"}),
        reprocess_skipped=False,
        reprocess_hwp_no_extractable_text=True,
    )
    ids = {str(t["id"]) for t in targets}
    out["fetch_includes_skipped_file"] = str(SKIPPED_FILE_ID) in ids

    dry, _ = run_process_pending_documents(
        settings,
        DS_ID,
        limit=1,
        max_file_size_bytes=268_435_456,
        include_extensions=frozenset({"hwp"}),
        dry_run=True,
        reprocess_skipped=False,
        reprocess_hwp_no_extractable_text=True,
    )
    out["dry_run_limit1_target_count"] = dry.get("target_count")

    ctx, err = _pending_document_webdav_context(settings, DS_ID)
    if err:
        out["webdav_error"] = err[0].get("message")
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 1

    with get_db_connection() as conn:
        outcome = _process_one_file(
            conn,
            ds_id=DS_ID,
            scan_job_id=None,
            row=row,
            server_url=str(ctx["server_url"]),
            webdav_root=str(ctx["webdav_root"]),
            uname=str(ctx["uname"]),
            password=str(ctx["password"]),
            timeout_seconds=float(settings.webdav_timeout_seconds),
            max_file_size_bytes=268_435_456,
            allowed_ext=frozenset({"hwp"}),
        )
        conn.commit()

    item = outcome.get("item") or {}
    out["process_kind"] = outcome.get("kind")
    out["process_status"] = item.get("status")
    out["process_parser"] = item.get("parser_name")
    out["after"] = _file_status(SKIPPED_FILE_ID)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    ok = (
        out.get("after", {}).get("analysis_status") == "COMPLETED"
        and out.get("after", {}).get("parser_name") == "hwp5html"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
