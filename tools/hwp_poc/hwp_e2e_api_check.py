#!/usr/bin/env python3
"""
HWP E2E API check helper (standalone; not imported by backend).

Automates parts of docs/07_아키텍처/hwp_e2e_검증계획.md against a running API.
Does not print tokens or full response bodies / extracted text.

Usage (safe — guidance only):
  python tools/hwp_poc/hwp_e2e_api_check.py --data-source-id <UUID> --token <JWT>

Dry-run documents:
  python tools/hwp_poc/hwp_e2e_api_check.py ... --dry-run-documents

Full pipeline slice (explicit flags):
  python tools/hwp_poc/hwp_e2e_api_check.py ... --run-documents --run-chunk --run-embedding --keyword "키워드"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_ENV_TOKEN = "INTERNAL_AI_SEARCH_TOKEN"
_SNIPPET_MAX = 200
_PREVIEW_TEXT_MAX = 300
_ITEM_PREVIEW_MAX = 25
_DEFAULT_TIMEOUT = 300


def _truncate(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    s = str(text).replace("\r\n", "\n").replace("\r", "\n")
    if len(s) <= limit:
        return s
    return s[:limit] + "…"


def _api_request(
    method: str,
    url: str,
    *,
    token: str,
    body: dict[str, Any] | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> tuple[int, dict[str, Any] | list[Any] | None, str | None]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    data: bytes | None = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return 0, None, f"network error: {exc.reason}"

    parsed: dict[str, Any] | list[Any] | None
    try:
        parsed = json.loads(raw) if raw.strip() else None
    except json.JSONDecodeError:
        return status, None, "response is not valid JSON"

    err_msg: str | None = None
    if status >= 400:
        if isinstance(parsed, dict):
            err_msg = (
                str(parsed.get("message") or parsed.get("detail") or parsed.get("error") or "")
            ).strip() or f"HTTP {status}"
        else:
            err_msg = f"HTTP {status}"
    elif isinstance(parsed, dict) and parsed.get("status") == "error":
        err_msg = str(parsed.get("message") or parsed.get("error") or "business error").strip()

    return status, parsed, err_msg


def _print_step_error(step: str, status: int, message: str | None) -> None:
    print(f"[FAIL] {step}: HTTP {status}" + (f" — {message}" if message else ""))


def _summarize_documents(step: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {"step": step, "ok": False}
    if not payload or not isinstance(payload, dict):
        out["error"] = "empty payload"
        return out

    out["status"] = payload.get("status")
    out["message"] = payload.get("message")
    out["target_count"] = payload.get("target_count")
    out["processed_count"] = payload.get("processed_count")
    out["completed_count"] = payload.get("completed_count")
    out["skipped_count"] = payload.get("skipped_count")
    out["failed_count"] = payload.get("failed_count")
    out["dry_run"] = payload.get("dry_run")
    items = payload.get("items") or []
    out["items_count"] = len(items) if isinstance(items, list) else 0

    item_rows: list[dict[str, Any]] = []
    if isinstance(items, list):
        for row in items[:_ITEM_PREVIEW_MAX]:
            if not isinstance(row, dict):
                continue
            item_rows.append(
                {
                    "file_id": row.get("file_id"),
                    "extension": row.get("extension"),
                    "status": row.get("status"),
                    "planned_action": row.get("planned_action"),
                    "reason": row.get("reason"),
                    "text_length": row.get("text_length"),
                    "parser_name": row.get("parser_name"),
                }
            )
    out["items_preview"] = item_rows
    out["ok"] = payload.get("status") == "ok"
    return out


def _summarize_chunk(payload: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {"step": "chunk-completed-text", "ok": False}
    if not payload or not isinstance(payload, dict):
        out["error"] = "empty payload"
        return out
    out["status"] = payload.get("status")
    out["message"] = payload.get("message")
    out["target_count"] = payload.get("target_count")
    out["processed_count"] = payload.get("processed_count")
    out["chunked_files_count"] = payload.get("chunked_files_count")
    out["skipped_count"] = payload.get("skipped_count")
    out["failed_count"] = payload.get("failed_count")
    out["created_chunks_count"] = payload.get("created_chunks_count")
    out["ok"] = payload.get("status") == "ok"
    return out


def _summarize_embed(payload: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {"step": "embed-pending-chunks", "ok": False}
    if not payload or not isinstance(payload, dict):
        out["error"] = "empty payload"
        return out
    out["status"] = payload.get("status")
    out["message"] = payload.get("message")
    out["target_chunks_count"] = payload.get("target_chunks_count")
    out["processed_chunks_count"] = payload.get("processed_chunks_count")
    out["embedded_chunks_count"] = payload.get("embedded_chunks_count")
    out["failed_chunks_count"] = payload.get("failed_chunks_count")
    out["completed_files_count"] = payload.get("completed_files_count")
    out["ok"] = payload.get("status") == "ok"
    return out


def _summarize_search(payload: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {"step": "search", "ok": False}
    if not payload or not isinstance(payload, dict):
        out["error"] = "empty payload"
        return out
    out["status"] = payload.get("status")
    out["message"] = payload.get("message")
    results = payload.get("results") or []
    out["total_results"] = payload.get("total_results", len(results) if isinstance(results, list) else 0)
    first: dict[str, Any] | None = None
    if isinstance(results, list) and results and isinstance(results[0], dict):
        r0 = results[0]
        first = {
            "file_id": r0.get("file_id"),
            "chunk_id": r0.get("chunk_id"),
            "start_line": r0.get("start_line"),
            "end_line": r0.get("end_line"),
            "score": r0.get("score"),
            "snippet": _truncate(r0.get("snippet"), _SNIPPET_MAX),
            "extension": r0.get("extension"),
        }
    out["first_result"] = first
    out["ok"] = payload.get("status") == "ok" and out["total_results"] > 0
    return out


def _summarize_preview(payload: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {"step": "preview", "ok": False}
    if not payload or not isinstance(payload, dict):
        out["error"] = "empty payload"
        return out
    out["status"] = payload.get("status")
    out["message"] = payload.get("message")
    preview = payload.get("preview") if isinstance(payload.get("preview"), dict) else {}
    out["start_line"] = preview.get("start_line")
    out["end_line"] = preview.get("end_line")
    out["line_count"] = preview.get("line_count")
    out["char_count"] = preview.get("char_count")
    out["text_preview"] = _truncate(preview.get("text"), _PREVIEW_TEXT_MAX)
    out["ok"] = payload.get("status") == "ok"
    return out


def _print_human_summary(summary: dict[str, Any]) -> None:
    print()
    print("=== HWP E2E API check summary ===")
    for key in ("runtime_guidance", "documents_dry_run", "documents_run", "chunk", "embedding", "search", "preview"):
        block = summary.get(key)
        if not block:
            continue
        if key == "runtime_guidance":
            print(f"\n[{key}]")
            for line in block.get("lines", []):
                print(f"  {line}")
            continue
        step = block.get("step", key)
        ok = block.get("ok")
        mark = "OK" if ok else "FAIL"
        print(f"\n[{mark}] {step}")
        for field in (
            "status",
            "message",
            "target_count",
            "processed_count",
            "completed_count",
            "skipped_count",
            "failed_count",
            "dry_run",
            "items_count",
            "chunked_files_count",
            "created_chunks_count",
            "embedded_chunks_count",
            "failed_chunks_count",
            "total_results",
            "start_line",
            "end_line",
            "line_count",
            "text_preview",
            "error",
        ):
            if field in block and block[field] is not None:
                print(f"  {field}: {block[field]}")
        if block.get("first_result"):
            print(f"  first_result: {json.dumps(block['first_result'], ensure_ascii=False)}")
        items = block.get("items_preview")
        if items:
            print(f"  items_preview ({len(items)} shown):")
            for row in items:
                print(
                    "    - "
                    f"file_id={row.get('file_id')} "
                    f"ext={row.get('extension')} "
                    f"status={row.get('status')} "
                    f"planned={row.get('planned_action')} "
                    f"reason={row.get('reason')} "
                    f"text_length={row.get('text_length')}"
                )
    if summary.get("no_actions"):
        print("\n[info] No mutating steps were requested. Use --dry-run-documents / --run-documents / …")


def _runtime_guidance() -> dict[str, Any]:
    lines = [
        "Run runtime check first (from repo root):",
        "  python tools/hwp_poc/check_hwp_runtime.py",
        "  python tools/hwp_poc/check_hwp_runtime.py --json",
        "Ensure backend API (uvicorn) is up and WebDAV samples are synced (sync-tree) before documents step.",
        "Record results in docs/07_아키텍처/hwp_e2e_검증결과_템플릿.md",
    ]
    print("\n[guidance] HWP runtime / prerequisites")
    for line in lines:
        print(f"  {line}")
    return {"lines": lines}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="HWP E2E API helper (no secrets or full bodies in output)"
    )
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--token", default=None, help="Admin Bearer JWT (or env INTERNAL_AI_SEARCH_TOKEN)")
    parser.add_argument("--data-source-id", required=True, help="Data source UUID")
    parser.add_argument("--keyword", default=None, help="Search keyword; omit to skip search/preview")
    parser.add_argument(
        "--include-preview",
        action="store_true",
        help="Call preview API for first search hit (needs --keyword)",
    )
    parser.add_argument("--limit", type=int, default=20, help="process-pending-documents limit")
    parser.add_argument(
        "--dry-run-documents",
        action="store_true",
        help="POST process-pending-documents?dry_run=true&include_extensions=hwp",
    )
    parser.add_argument(
        "--run-documents",
        action="store_true",
        help="POST process-pending-documents (mutating)",
    )
    parser.add_argument("--run-chunk", action="store_true", help="POST chunk-completed-text")
    parser.add_argument("--run-embedding", action="store_true", help="POST embed-pending-chunks")
    parser.add_argument("--json", action="store_true", dest="json_out", help="Print JSON summary only")
    args = parser.parse_args()

    token = (args.token or os.environ.get(_ENV_TOKEN) or "").strip()
    if not token:
        print("error: --token or INTERNAL_AI_SEARCH_TOKEN is required", file=sys.stderr)
        return 2

    base = args.base_url.rstrip("/")
    ds_id = args.data_source_id.strip()
    summary: dict[str, Any] = {
        "base_url": base,
        "data_source_id": ds_id,
        "options": {
            "limit": args.limit,
            "dry_run_documents": args.dry_run_documents,
            "run_documents": args.run_documents,
            "run_chunk": args.run_chunk,
            "run_embedding": args.run_embedding,
            "keyword": args.keyword,
            "include_preview": args.include_preview,
        },
    }

    summary["runtime_guidance"] = _runtime_guidance()

    any_action = (
        args.dry_run_documents
        or args.run_documents
        or args.run_chunk
        or args.run_embedding
        or bool(args.keyword)
    )
    if not any_action:
        summary["no_actions"] = True
        if args.json_out:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            _print_human_summary(summary)
            print(
                "\nTip: --dry-run-documents | --run-documents | --run-chunk | "
                "--run-embedding | --keyword <text> [--include-preview]"
            )
        return 0

    failed = False

    if args.dry_run_documents:
        q = urllib.parse.urlencode(
            {
                "dry_run": "true",
                "limit": str(max(1, args.limit)),
                "include_extensions": "hwp",
            }
        )
        url = f"{base}/api/data-sources/{ds_id}/process-pending-documents?{q}"
        status, payload, err = _api_request("POST", url, token=token)
        block = _summarize_documents("documents-dry-run", payload if isinstance(payload, dict) else None)
        if err or status >= 400:
            _print_step_error("documents-dry-run", status, err)
            block["ok"] = False
            block["http_status"] = status
            block["error"] = err
            failed = True
        summary["documents_dry_run"] = block
        if not args.json_out:
            print(
                f"\n[documents-dry-run] target_count={block.get('target_count')} "
                f"items={block.get('items_count')} status={block.get('status')}"
            )

    if args.run_documents:
        q = urllib.parse.urlencode(
            {"limit": str(max(1, args.limit)), "include_extensions": "hwp"}
        )
        url = f"{base}/api/data-sources/{ds_id}/process-pending-documents?{q}"
        status, payload, err = _api_request("POST", url, token=token)
        block = _summarize_documents("documents-run", payload if isinstance(payload, dict) else None)
        if err or status >= 400:
            _print_step_error("documents-run", status, err)
            block["ok"] = False
            block["http_status"] = status
            block["error"] = err
            failed = True
        summary["documents_run"] = block
        if not args.json_out:
            print(
                f"\n[documents-run] completed={block.get('completed_count')} "
                f"skipped={block.get('skipped_count')} failed={block.get('failed_count')}"
            )

    if args.run_chunk:
        q = urllib.parse.urlencode({"limit": "100", "include_extensions": "hwp"})
        url = f"{base}/api/data-sources/{ds_id}/chunk-completed-text?{q}"
        status, payload, err = _api_request("POST", url, token=token)
        block = _summarize_chunk(payload if isinstance(payload, dict) else None)
        if err or status >= 400:
            _print_step_error("chunk-completed-text", status, err)
            block["ok"] = False
            block["http_status"] = status
            block["error"] = err
            failed = True
        summary["chunk"] = block
        if not args.json_out:
            print(
                f"\n[chunk] chunked_files={block.get('chunked_files_count')} "
                f"created_chunks={block.get('created_chunks_count')} "
                f"failed={block.get('failed_count')}"
            )

    if args.run_embedding:
        q = urllib.parse.urlencode(
            {
                "limit": "500",
                "batch_size": "32",
                "include_extensions": "hwp",
            }
        )
        url = f"{base}/api/data-sources/{ds_id}/embed-pending-chunks?{q}"
        status, payload, err = _api_request("POST", url, token=token)
        block = _summarize_embed(payload if isinstance(payload, dict) else None)
        if err or status >= 400:
            _print_step_error("embed-pending-chunks", status, err)
            block["ok"] = False
            block["http_status"] = status
            block["error"] = err
            failed = True
        summary["embedding"] = block
        if not args.json_out:
            print(
                f"\n[embedding] embedded_chunks={block.get('embedded_chunks_count')} "
                f"failed={block.get('failed_chunks_count')}"
            )

    search_first: dict[str, Any] | None = None
    if args.keyword:
        url = f"{base}/api/search"
        body = {
            "query": args.keyword,
            "data_source_id": ds_id,
            "include_extensions": ["hwp"],
            "limit": 5,
        }
        status, payload, err = _api_request("POST", url, token=token, body=body)
        block = _summarize_search(payload if isinstance(payload, dict) else None)
        if err or status >= 400:
            _print_step_error("search", status, err)
            block["ok"] = False
            block["http_status"] = status
            block["error"] = err
            failed = True
        else:
            search_first = block.get("first_result")
        summary["search"] = block
        if not args.json_out:
            print(f"\n[search] total_results={block.get('total_results')}")
            if search_first:
                print(f"  first: {json.dumps(search_first, ensure_ascii=False)}")

    if args.include_preview:
        if not args.keyword:
            print("\n[skip] preview: --keyword is required", file=sys.stderr)
        elif not search_first or not search_first.get("file_id") or not search_first.get("chunk_id"):
            print("\n[skip] preview: no search hit with file_id/chunk_id")
        else:
            fid = search_first["file_id"]
            cid = search_first["chunk_id"]
            q = urllib.parse.urlencode(
                {
                    "chunk_id": str(cid),
                    "context_lines": "5",
                    "max_chars": "4000",
                }
            )
            url = f"{base}/api/files/{fid}/preview?{q}"
            status, payload, err = _api_request("GET", url, token=token)
            block = _summarize_preview(payload if isinstance(payload, dict) else None)
            if err or status >= 400:
                _print_step_error("preview", status, err)
                block["ok"] = False
                block["http_status"] = status
                block["error"] = err
                failed = True
            summary["preview"] = block
            if not args.json_out:
                print(
                    f"\n[preview] lines {block.get('start_line')}–{block.get('end_line')} "
                    f"chars={block.get('char_count')}"
                )

    summary["overall_ok"] = not failed

    if args.json_out:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        _print_human_summary(summary)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
