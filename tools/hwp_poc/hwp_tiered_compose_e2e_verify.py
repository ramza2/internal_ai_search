#!/usr/bin/env python3
"""
Compose-tiered HWP E2E verification (runs inside backend container).

Uses app services directly (no JWT). Does not print extracted text or credentials.
Writes JSON summary to stdout; host may redirect to tmp/hwp_poc/tiered_e2e_report.json.

Usage (repo root):
  docker compose --env-file backend/.env -f docker-compose.dev.yml exec -T backend \\
    python tools/hwp_poc/hwp_tiered_compose_e2e_verify.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from uuid import UUID

_APP_ROOT = Path(__file__).resolve().parents[2]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

# Optional overrides (file UUIDs in compose DB)
_TABLE_FORM_FILE_ID = os.environ.get(
    "TIERED_E2E_TABLE_FORM_FILE_ID", "c5fd2074-ba09-4591-b312-1889143f5350"
)
_BODY_HWP_FILE_ID = os.environ.get(
    "TIERED_E2E_BODY_FILE_ID", ""
)  # auto-pick if empty
_KEYWORDS = ("품목(문제)명", "관리번호", "에이전틱 AI", "--- table 1 ---")


def _keyword_checks(text: str) -> dict[str, bool | int]:
    lower = text.lower()
    out: dict[str, bool | int] = {}
    for kw in _KEYWORDS:
        if kw.startswith("---"):
            out["has_table_marker"] = kw in text
        else:
            key = f"hit_{kw.replace(' ', '_')}"
            out[key] = lower.count(kw.lower())
    return out


def _fetch_file_row(file_id: UUID) -> dict[str, Any] | None:
    from app.db.database import get_db_connection
    from psycopg.rows import dict_row

    sql = """
        SELECT f.id, f.data_source_id, f.remote_path, f.extension, f.size_bytes,
               f.analysis_status::text AS analysis_status,
               f.analysis_error_code, f.content_hash
        FROM files f WHERE f.id = %s
    """
    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(sql, (file_id,))
            row = cur.fetchone()
    return dict(row) if row else None


def _file_status(file_id: UUID) -> dict[str, Any]:
    from app.db.database import get_db_connection
    from psycopg.rows import dict_row

    sql = """
        SELECT f.analysis_status::text AS analysis_status,
               f.analysis_error_code,
               fc.text_length,
               fc.parser_name,
               fc.parser_version
        FROM files f
        LEFT JOIN file_contents fc ON fc.file_id = f.id
        WHERE f.id = %s
    """
    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(sql, (file_id,))
            row = cur.fetchone()
    return dict(row) if row else {}


def _pick_body_pending_id(ds_id: UUID) -> str | None:
    from app.db.database import get_db_connection
    from psycopg.rows import dict_row

    sql = """
        SELECT f.id::text
        FROM files f
        WHERE f.data_source_id = %s
          AND lower(f.extension) = 'hwp'
          AND f.analysis_status = 'PENDING'
          AND f.size_bytes BETWEEN 40000 AND 250000
        ORDER BY f.size_bytes DESC
        LIMIT 1
    """
    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(sql, (ds_id,))
            row = cur.fetchone()
    return str(row["id"]) if row else None


def _process_file_by_id(file_id: UUID, *, alias: str) -> dict[str, Any]:
    from app.core.config import settings
    from app.parsers.registry import supported_document_extensions
    from app.services.pending_document_processor_service import (
        _pending_document_webdav_context,
        _process_one_file,
    )

    row = _fetch_file_row(file_id)
    if not row:
        return {"alias": alias, "ok": False, "error": "file not found"}

    ds_id = UUID(str(row["data_source_id"]))
    ctx, err = _pending_document_webdav_context(settings, ds_id)
    if err:
        return {"alias": alias, "ok": False, "error": f"webdav context: {err[0]}"}

    allowed = supported_document_extensions()
    from app.db.database import get_db_connection

    t0 = time.perf_counter()
    with get_db_connection() as conn:
        outcome = _process_one_file(
            conn,
            ds_id=ds_id,
            scan_job_id=None,
            row=row,
            server_url=str(ctx["server_url"]),
            webdav_root=str(ctx["webdav_root"]),
            uname=str(ctx["uname"]),
            password=str(ctx["password"]),
            timeout_seconds=float(settings.webdav_timeout_seconds),
            max_file_size_bytes=52_428_800,
            allowed_ext=allowed,
        )
        conn.commit()
    elapsed = round(time.perf_counter() - t0, 2)

    item = outcome.get("item") or {}
    st = _file_status(file_id)
    checks: dict[str, Any] = {}
    if st.get("text_length"):
        from app.db.database import get_db_connection
        from psycopg.rows import dict_row

        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT extracted_text FROM file_contents WHERE file_id = %s",
                    (file_id,),
                )
                r = cur.fetchone()
        if r and r.get("extracted_text"):
            checks = _keyword_checks(str(r["extracted_text"]))

    return {
        "alias": alias,
        "file_id": str(file_id),
        "size_bytes": row.get("size_bytes"),
        "ok": outcome.get("kind") in ("completed", "unchanged")
        or item.get("status") == "COMPLETED",
        "kind": outcome.get("kind"),
        "item_status": item.get("status"),
        "item_reason": item.get("reason"),
        "parser_name": st.get("parser_name"),
        "text_length": st.get("text_length"),
        "analysis_status": st.get("analysis_status"),
        "analysis_error_code": st.get("analysis_error_code"),
        "elapsed_seconds": elapsed,
        "keyword_checks": checks,
    }


def main() -> int:
    from app.core.config import settings
    from app.db.database import get_db_connection
    from psycopg.rows import dict_row
    from tools.hwp_poc.check_hwp_runtime import run_check

    report: dict[str, Any] = {
        "verification": "hwp_tiered_compose_e2e",
        "hwp_extraction_strategy": settings.hwp_extraction_strategy,
    }

    runtime = run_check(
        hwp5txt_bin=settings.hwp5txt_bin,
        hwp5html_bin=settings.hwp5html_bin,
        timeout_seconds=10.0,
        extraction_strategy=settings.hwp_extraction_strategy,
    )
    report["runtime_check"] = {
        "status": runtime.get("status"),
        "hwp5txt_found": runtime.get("hwp5txt_found"),
        "hwp5txt_help_ok": runtime.get("hwp5txt_help_ok"),
        "hwp5html_found": runtime.get("hwp5html_found"),
        "hwp5html_help_ok": runtime.get("hwp5html_help_ok"),
        "hwp_extraction_strategy": runtime.get("hwp_extraction_strategy"),
        "imports_ok": all(runtime.get("imports", {}).values()),
    }
    if runtime.get("status") != "ok":
        report["verdict"] = "No-Go"
        report["verdict_reason"] = "runtime check failed"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id::text FROM data_sources WHERE is_active = true ORDER BY created_at LIMIT 1"
            )
            ds_row = cur.fetchone()
    if not ds_row:
        report["verdict"] = "No-Go"
        report["verdict_reason"] = "no active data source"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    ds_id = UUID(str(ds_row["id"]))
    report["data_source_id"] = str(ds_id)

    # Skipped baseline (pre-tiered) — status only
    skipped_id = os.environ.get(
        "TIERED_E2E_SKIPPED_BASELINE_ID", "9f69bb54-b4a2-4c2e-914b-d95cc76bf3f4"
    )
    report["skipped_baseline"] = _file_status(UUID(skipped_id))

    doc_results: list[dict[str, Any]] = []
    table_id = UUID(_TABLE_FORM_FILE_ID)
    doc_results.append(_process_file_by_id(table_id, alias="table-form-hwp"))

    body_id_str = _BODY_HWP_FILE_ID.strip() or (_pick_body_pending_id(ds_id) or "")
    if body_id_str:
        doc_results.append(_process_file_by_id(UUID(body_id_str), alias="body-hwp"))
    report["documents"] = doc_results

    table_ok = any(
        d.get("alias") == "table-form-hwp" and d.get("ok") and (d.get("text_length") or 0) > 1000
        for d in doc_results
    )

    chunk_block: dict[str, Any] = {"ok": False}
    embed_block: dict[str, Any] = {"ok": False}
    search_block: dict[str, Any] = {"ok": False}

    if table_ok:
        from app.services.chunk_text_processor_service import run_chunk_completed_text_core
        from app.services.chunk_embedding_service import run_embed_pending_chunks_core
        from app.schemas.search import SearchRequest
        from app.services.search_service import run_search

        t0 = time.perf_counter()
        chunk_res = run_chunk_completed_text_core(
            ds_id,
            limit=20,
            chunk_size=1200,
            chunk_overlap=200,
            min_chunk_size=100,
            reprocess=False,
            include_extensions=frozenset({"hwp"}),
            scan_job_id=None,
        )
        chunk_block = {
            "ok": chunk_res.payload.get("status") == "ok",
            "elapsed_seconds": round(time.perf_counter() - t0, 2),
            "chunked_files_count": chunk_res.payload.get("chunked_files_count"),
            "created_chunks_count": chunk_res.payload.get("created_chunks_count"),
            "failed_count": chunk_res.payload.get("failed_count"),
        }

        t0 = time.perf_counter()
        embed_res = run_embed_pending_chunks_core(
            settings,
            ds_id,
            ds_name=None,
            rows=None,
            limit=500,
            batch_size=32,
            include_extensions=frozenset({"hwp"}),
            reembed=False,
            file_id=None,
            scan_job_id=None,
        )
        embed_block = {
            "ok": embed_res.payload.get("status") == "ok",
            "elapsed_seconds": round(time.perf_counter() - t0, 2),
            "embedded_chunks_count": embed_res.payload.get("embedded_chunks_count"),
            "failed_chunks_count": embed_res.payload.get("failed_chunks_count"),
        }

        for kw in ("관리번호", "품목(문제)명", "에이전틱 AI"):
            t0 = time.perf_counter()
            req = SearchRequest(
                query=kw,
                data_source_id=ds_id,
                include_extensions=["hwp"],
                limit=5,
            )
            try:
                resp = run_search(settings, req)
                hits = resp.total_results if hasattr(resp, "total_results") else len(resp.results or [])
                search_block[kw] = {
                    "ok": hits > 0,
                    "total_results": hits,
                    "elapsed_seconds": round(time.perf_counter() - t0, 2),
                    "first_file_id": (
                        str(resp.results[0].file_id) if resp.results else None
                    ),
                    "first_start_line": (
                        resp.results[0].start_line if resp.results else None
                    ),
                }
            except Exception as exc:
                search_block[kw] = {"ok": False, "error": type(exc).__name__}

        search_block["ok"] = any(
            isinstance(v, dict) and v.get("ok") for k, v in search_block.items() if k != "ok"
        )

    report["chunk"] = chunk_block
    report["embedding"] = embed_block
    report["search"] = search_block

    table_doc = next((d for d in doc_results if d.get("alias") == "table-form-hwp"), {})
    report["performance"] = {
        "table_form_elapsed_seconds": table_doc.get("elapsed_seconds"),
        "poc_reference": {
            "hwp5txt_seconds": "1.8-2.1",
            "hwp5html_seconds": "8.1-8.5",
            "note": "tiered runs hwp5html first; large table-form HWP may take ~8-15s per file",
        },
    }

    if runtime.get("status") == "ok" and table_ok and chunk_block.get("ok") and embed_block.get(
        "ok"
    ) and search_block.get("ok"):
        report["verdict"] = "Go"
    elif runtime.get("status") == "ok" and table_ok:
        report["verdict"] = "조건부 Go"
        report["verdict_reason"] = "documents OK; chunk/search partial or pending"
    else:
        report["verdict"] = "No-Go"

    report["rollback"] = {
        "env": "HWP_EXTRACTION_STRATEGY=hwp5txt_only",
        "documented_in": "backend/README.md",
    }
    report["reprocess_policy"] = {
        "note": "COMPLETED/SKIPPED HWP are not auto-reprocessed after parser upgrade",
        "skipped_baseline_stays_skipped": report["skipped_baseline"].get("analysis_status")
        == "SKIPPED",
        "follow_up": "admin selective reprocess or new WebDAV path sync recommended",
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("verdict") in ("Go", "조건부 Go") else 1


if __name__ == "__main__":
    raise SystemExit(main())
