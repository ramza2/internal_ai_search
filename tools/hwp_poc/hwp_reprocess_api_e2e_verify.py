#!/usr/bin/env python3
"""
HWP SKIPPED/NO_EXTRACTABLE_TEXT explicit reprocess — HTTP API E2E verifier.

Reads admin credentials from environment only (never prints passwords or JWT).
Optional: loads KEY=VALUE pairs from backend/.env if present (gitignored).

Usage:
  set E2E_ADMIN_LOGIN_ID / E2E_ADMIN_PASSWORD in backend/.env
  python tools/hwp_poc/hwp_reprocess_api_e2e_verify.py \\
    --base-url http://localhost:8000 \\
    --data-source-id <UUID> \\
    --keyword "관리번호" \\
    --limit 1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_BACKEND = _REPO_ROOT / "backend" / ".env"
_DEFAULT_TIMEOUT = 300
_JOB_POLL_SEC = 2.0
_JOB_POLL_MAX = 600


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        val = val.strip().strip('"').strip("'")
        os.environ[key] = val


def _api_request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> tuple[int, dict[str, Any] | list[Any] | None, str | None]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
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

    try:
        parsed = json.loads(raw) if raw.strip() else None
    except json.JSONDecodeError:
        return status, None, "response is not valid JSON"

    err: str | None = None
    if status >= 400:
        if isinstance(parsed, dict):
            err = str(
                parsed.get("message") or parsed.get("detail") or parsed.get("error") or ""
            ).strip() or f"HTTP {status}"
        else:
            err = f"HTTP {status}"
    elif isinstance(parsed, dict) and parsed.get("status") == "error":
        err = str(parsed.get("message") or parsed.get("error") or "business error").strip()
    return status, parsed, err


def _login(base: str) -> str:
    lid = (os.environ.get("E2E_ADMIN_LOGIN_ID") or os.environ.get("INITIAL_ADMIN_LOGIN_ID") or "admin").strip()
    pwd = (os.environ.get("E2E_ADMIN_PASSWORD") or "").strip()
    if not pwd or pwd == "CHANGE_ME":
        raise RuntimeError(
            "Set E2E_ADMIN_PASSWORD in backend/.env (current admin password; "
            "INITIAL_ADMIN_PASSWORD is bootstrap-only after a password change)"
        )
    status, data, err = _api_request(
        "POST",
        f"{base}/api/auth/login",
        body={"login_id": lid, "password": pwd},
    )
    if status != 200 or not isinstance(data, dict):
        raise RuntimeError(f"login failed: {err}")
    token = data.get("access_token") or data.get("token")
    if not token:
        raise RuntimeError("login response missing token")
    return str(token)


def _summarize_documents(payload: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False}
    if not payload:
        return out
    out["status"] = payload.get("status")
    out["target_count"] = payload.get("target_count")
    out["completed_count"] = payload.get("completed_count")
    out["skipped_count"] = payload.get("skipped_count")
    out["failed_count"] = payload.get("failed_count")
    out["dry_run"] = payload.get("dry_run")
    out["warnings"] = payload.get("warnings")
    items = payload.get("items") or []
    rows: list[dict[str, Any]] = []
    if isinstance(items, list):
        for row in items[:10]:
            if not isinstance(row, dict):
                continue
            rows.append(
                {
                    "file_id": row.get("file_id"),
                    "extension": row.get("extension"),
                    "planned_action": row.get("planned_action"),
                    "status": row.get("status"),
                    "parser_name": row.get("parser_name"),
                    "reason": row.get("reason"),
                }
            )
    out["items_preview"] = rows
    out["ok"] = str(payload.get("status") or "").lower() == "ok"
    return out


def _poll_job(base: str, token: str, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + _JOB_POLL_MAX
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        status, data, err = _api_request("GET", f"{base}/api/admin/jobs/{job_id}", token=token)
        if err or not isinstance(data, dict):
            last = {"ok": False, "error": err, "http_status": status}
            time.sleep(_JOB_POLL_SEC)
            continue
        job = data.get("job") if isinstance(data.get("job"), dict) else data
        st = str(job.get("status") or "").upper()
        last = {
            "ok": True,
            "status": st,
            "processed_files": job.get("processed_files"),
            "completed_files": job.get("completed_files"),
            "failed_files": job.get("failed_files"),
            "skipped_files": job.get("skipped_files"),
            "error_message": job.get("error_message"),
            "job_params": {
                k: job.get("job_params", {}).get(k)
                for k in ("reprocess_hwp_no_extractable_text", "include_extensions", "limit")
                if isinstance(job.get("job_params"), dict)
            }
            if isinstance(job.get("job_params"), dict)
            else None,
        }
        if st in ("COMPLETED", "FAILED", "CANCELLED"):
            last["terminal"] = True
            return last
        time.sleep(_JOB_POLL_SEC)
    last["timeout"] = True
    return last


def main() -> int:
    _load_dotenv(_ENV_BACKEND)

    parser = argparse.ArgumentParser(description="HWP SKIPPED reprocess HTTP E2E (no secrets in output)")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--data-source-id", required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--keyword", default="관리번호")
    parser.add_argument("--skip-run", action="store_true", help="Only login + dry_run")
    parser.add_argument("--use-sync-api", action="store_true", help="Use data-sources API instead of admin job")
    parser.add_argument("--json", action="store_true", dest="json_out")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    ds_id = args.data_source_id.strip()
    summary: dict[str, Any] = {
        "base_url": base,
        "data_source_id": ds_id,
        "limit": args.limit,
        "keyword": args.keyword,
    }
    failed = False

    try:
        token = _login(base)
        summary["login"] = {"ok": True}
    except RuntimeError as exc:
        summary["login"] = {"ok": False, "error": str(exc)}
        if args.json_out:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(f"[FAIL] login: {exc}", file=sys.stderr)
        return 2

    q_base = {
        "limit": str(max(1, args.limit)),
        "include_extensions": "hwp",
        "reprocess_hwp_no_extractable_text": "true",
    }
    q_dry = urllib.parse.urlencode({**q_base, "dry_run": "true"})
    url_dry = f"{base}/api/data-sources/{ds_id}/process-pending-documents?{q_dry}"
    st, payload, err = _api_request("POST", url_dry, token=token)
    block = _summarize_documents(payload if isinstance(payload, dict) else None)
    if err or st >= 400:
        block["ok"] = False
        block["error"] = err
        failed = True
    summary["dry_run"] = block
    if (block.get("target_count") or 0) < 1:
        summary["dry_run"]["note"] = "no SKIPPED/NO_EXTRACTABLE_TEXT hwp targets — check data source"
        failed = True

    if args.skip_run:
        summary["overall_ok"] = not failed
        if args.json_out:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1 if failed else 0

    if args.use_sync_api:
        q_run = urllib.parse.urlencode(q_base)
        url_run = f"{base}/api/data-sources/{ds_id}/process-pending-documents?{q_run}"
        st, payload, err = _api_request("POST", url_run, token=token, timeout=900)
        summary["documents_run"] = _summarize_documents(payload if isinstance(payload, dict) else None)
        if err or st >= 400:
            summary["documents_run"]["error"] = err
            failed = True
    else:
        body = {
            "data_source_id": ds_id,
            "limit": max(1, args.limit),
            "include_extensions": "hwp",
            "reprocess_skipped": False,
            "reprocess_hwp_no_extractable_text": True,
            "priority": 0,
        }
        st, payload, err = _api_request(
            "POST",
            f"{base}/api/admin/jobs/process-pending-documents",
            token=token,
            body=body,
        )
        enqueue: dict[str, Any] = {"ok": st == 200 and not err}
        if isinstance(payload, dict):
            enqueue["job_id"] = payload.get("job_id")
        if err:
            enqueue["error"] = err
            failed = True
        summary["job_enqueue"] = enqueue
        jid = enqueue.get("job_id")
        if jid:
            summary["job_poll"] = _poll_job(base, token, str(jid))
            if summary["job_poll"].get("status") != "COMPLETED":
                failed = True

    q_chunk = urllib.parse.urlencode({"limit": "100", "include_extensions": "hwp"})
    st, payload, err = _api_request(
        "POST",
        f"{base}/api/data-sources/{ds_id}/chunk-completed-text?{q_chunk}",
        token=token,
    )
    summary["chunk"] = {
        "ok": st == 200 and not err,
        "created_chunks_count": (payload or {}).get("created_chunks_count") if isinstance(payload, dict) else None,
        "failed_count": (payload or {}).get("failed_count") if isinstance(payload, dict) else None,
    }
    if err or st >= 400:
        summary["chunk"]["error"] = err
        failed = True

    q_emb = urllib.parse.urlencode({"limit": "500", "batch_size": "32", "include_extensions": "hwp"})
    st, payload, err = _api_request(
        "POST",
        f"{base}/api/data-sources/{ds_id}/embed-pending-chunks?{q_emb}",
        token=token,
        timeout=900,
    )
    summary["embedding"] = {
        "ok": st == 200 and not err,
        "embedded_chunks_count": (payload or {}).get("embedded_chunks_count") if isinstance(payload, dict) else None,
    }
    if err or st >= 400:
        summary["embedding"]["error"] = err
        failed = True

    st, payload, err = _api_request(
        "POST",
        f"{base}/api/search",
        token=token,
        body={
            "query": args.keyword,
            "data_source_id": ds_id,
            "include_extensions": ["hwp"],
            "limit": 5,
        },
    )
    search_first: dict[str, Any] | None = None
    if isinstance(payload, dict):
        results = payload.get("results") or []
        if results and isinstance(results[0], dict):
            search_first = {
                "file_id": results[0].get("file_id"),
                "chunk_id": results[0].get("chunk_id"),
                "score": results[0].get("score"),
            }
    summary["search"] = {
        "ok": st == 200 and not err,
        "total_results": (payload or {}).get("total_results") if isinstance(payload, dict) else None,
        "first_result": search_first,
    }
    if err or st >= 400:
        summary["search"]["error"] = err
        failed = True

    if search_first and search_first.get("file_id") and search_first.get("chunk_id"):
        fid, cid = search_first["file_id"], search_first["chunk_id"]
        q_prev = urllib.parse.urlencode(
            {"chunk_id": str(cid), "context_lines": "5", "max_chars": "4000"}
        )
        st, payload, err = _api_request(
            "GET",
            f"{base}/api/files/{fid}/preview?{q_prev}",
            token=token,
        )
        summary["preview"] = {
            "ok": st == 200 and not err,
            "char_count": (payload or {}).get("char_count") if isinstance(payload, dict) else None,
            "start_line": (payload or {}).get("start_line") if isinstance(payload, dict) else None,
        }
        if err or st >= 400:
            summary["preview"]["error"] = err
            failed = True

        st, payload, err = _api_request(
            "POST",
            f"{base}/api/answer",
            token=token,
            body={
                "query": args.keyword,
                "data_source_id": ds_id,
                "include_extensions": ["hwp"],
                "limit": 5,
                "context_limit": 5,
                "dry_run": False,
            },
            timeout=600,
        )
        citations = 0
        if isinstance(payload, dict):
            cites = payload.get("citations") or payload.get("sources") or []
            if isinstance(cites, list):
                citations = len(cites)
        summary["answer"] = {
            "ok": st == 200 and not err,
            "citations_count": citations,
            "has_answer_text": bool((payload or {}).get("answer")) if isinstance(payload, dict) else False,
        }
        if err or st >= 400:
            summary["answer"]["error"] = err
            failed = True

    summary["overall_ok"] = not failed
    if args.json_out:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
