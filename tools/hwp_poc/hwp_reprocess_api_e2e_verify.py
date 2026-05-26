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
    --only-reprocess-hwp-no-extractable-text \\
    --limit 1 \\
    --keyword "관리번호"
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
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

_VALID_ONLY_PLANNED = frozenset(
    {
        "REPROCESS_HWP_NO_EXTRACTABLE_TEXT_ONLY",
        "REPROCESS_HWP_NO_EXTRACTABLE_TEXT",
    }
)

_FIXTURE_RESET_SCRIPT = _REPO_ROOT / "tools" / "hwp_poc" / "hwp_skipped_fixture_reset.py"
_DEFAULT_BACKEND_CONTAINER = "internal_ai_search-backend-1"

_FIXTURE_ZERO_HINT = (
    "No SKIPPED/NO_EXTRACTABLE_TEXT HWP in this data source. "
    "A previous only-mode E2E likely already set skipped-baseline to COMPLETED. "
    "For compose dev, run once: "
    "docker cp tools/hwp_poc/hwp_skipped_fixture_reset.py "
    f"{_DEFAULT_BACKEND_CONTAINER}:/tmp/hwp_skipped_fixture_reset.py && "
    f"docker exec {_DEFAULT_BACKEND_CONTAINER} python /tmp/hwp_skipped_fixture_reset.py "
    "Or re-run with --prepare-skipped-fixture (same docker steps, automated)."
)


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
    lid = (
        os.environ.get("E2E_ADMIN_LOGIN_ID")
        or os.environ.get("INITIAL_ADMIN_LOGIN_ID")
        or "admin"
    ).strip()
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
                    "analysis_status_before": row.get("analysis_status_before"),
                    "analysis_error_code_before": row.get("analysis_error_code_before"),
                }
            )
    out["items_preview"] = rows
    out["ok"] = str(payload.get("status") or "").lower() == "ok"
    return out


def _validate_dry_run_target(
    block: dict[str, Any],
    *,
    only_mode: bool,
) -> tuple[bool, str | None, dict[str, Any] | None]:
    """Return (ok, error_message, first_item)."""
    if not block.get("ok"):
        return False, block.get("error") or "dry_run not ok", None
    tc = block.get("target_count") or 0
    if tc < 1:
        return False, "dry_run target_count is 0 — no SKIPPED HWP to reprocess", None
    items = block.get("items_preview") or []
    if not items:
        return False, "dry_run items_preview empty", None
    first = items[0]
    if only_mode:
        pa = str(first.get("planned_action") or "")
        if pa not in _VALID_ONLY_PLANNED:
            return False, f"first planned_action is {pa!r}, expected ONLY reprocess", first
        if str(first.get("analysis_status_before") or "").upper() != "SKIPPED":
            return (
                False,
                "first target analysis_status_before is not SKIPPED",
                first,
            )
        if str(first.get("analysis_error_code_before") or "").upper() != "NO_EXTRACTABLE_TEXT":
            return (
                False,
                "first target analysis_error_code_before is not NO_EXTRACTABLE_TEXT",
                first,
            )
    return True, None, first


def _documents_query_params(
    *,
    limit: int,
    only_mode: bool,
    dry_run: bool,
) -> dict[str, str]:
    q: dict[str, str] = {"limit": str(max(1, limit))}
    if only_mode:
        q["only_reprocess_hwp_no_extractable_text"] = "true"
    else:
        q["include_extensions"] = "hwp"
        q["reprocess_hwp_no_extractable_text"] = "true"
    if dry_run:
        q["dry_run"] = "true"
    return q


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
                for k in (
                    "only_reprocess_hwp_no_extractable_text",
                    "reprocess_hwp_no_extractable_text",
                    "include_extensions",
                    "limit",
                )
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


def _try_prepare_skipped_fixture(
    *,
    container: str,
) -> dict[str, Any]:
    """Reset compose-dev skipped-baseline via docker exec (no secrets in output)."""
    out: dict[str, Any] = {"attempted": True, "container": container}
    if not _FIXTURE_RESET_SCRIPT.is_file():
        out["ok"] = False
        out["error"] = "fixture reset script not found"
        return out
    cp = subprocess.run(
        [
            "docker",
            "cp",
            str(_FIXTURE_RESET_SCRIPT),
            f"{container}:/tmp/hwp_skipped_fixture_reset.py",
        ],
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0:
        out["ok"] = False
        out["error"] = (cp.stderr or cp.stdout or "docker cp failed").strip()[:200]
        return out
    ex = subprocess.run(
        ["docker", "exec", container, "python", "/tmp/hwp_skipped_fixture_reset.py"],
        capture_output=True,
        text=True,
    )
    if ex.returncode != 0:
        out["ok"] = False
        out["error"] = (ex.stderr or ex.stdout or "docker exec failed").strip()[:200]
        return out
    out["ok"] = "fixture_reset_ok" in (ex.stdout or "")
    if not out["ok"]:
        out["error"] = "unexpected fixture reset output"
    return out


def _extract_preview_fields(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"ok": False}
    prev = payload.get("preview") if isinstance(payload.get("preview"), dict) else payload
    return {
        "ok": True,
        "char_count": prev.get("char_count"),
        "start_line": prev.get("start_line"),
        "end_line": prev.get("end_line"),
    }


def main() -> int:
    _load_dotenv(_ENV_BACKEND)

    parser = argparse.ArgumentParser(description="HWP SKIPPED reprocess HTTP E2E (no secrets in output)")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--data-source-id", required=True)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--keyword", default="관리번호")
    parser.add_argument(
        "--only-reprocess-hwp-no-extractable-text",
        action="store_true",
        help="SKIPPED/NO_EXTRACTABLE_TEXT HWP only (excludes PENDING backlog)",
    )
    parser.add_argument(
        "--prepare-skipped-fixture",
        action="store_true",
        help="Before dry_run (only mode): reset compose-dev skipped-baseline via docker exec",
    )
    parser.add_argument(
        "--backend-container",
        default=_DEFAULT_BACKEND_CONTAINER,
        help=f"Container name for --prepare-skipped-fixture (default: {_DEFAULT_BACKEND_CONTAINER})",
    )
    parser.add_argument("--skip-run", action="store_true", help="Only login + dry_run")
    parser.add_argument("--use-sync-api", action="store_true", help="Use data-sources API instead of admin job")
    parser.add_argument("--json", action="store_true", dest="json_out")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    ds_id = args.data_source_id.strip()
    only_mode = bool(args.only_reprocess_hwp_no_extractable_text)
    summary: dict[str, Any] = {
        "base_url": base,
        "data_source_id": ds_id,
        "limit": args.limit,
        "keyword": args.keyword,
        "only_reprocess_hwp_no_extractable_text": only_mode,
    }
    failed = False
    target_file_id: str | None = None

    try:
        token = _login(base)
        summary["login"] = {"ok": True}
    except RuntimeError as exc:
        summary["login"] = {"ok": False, "error": str(exc)}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2

    if args.prepare_skipped_fixture:
        if not only_mode:
            summary["prepare_fixture"] = {
                "ok": False,
                "error": "--prepare-skipped-fixture requires --only-reprocess-hwp-no-extractable-text",
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 2
        summary["prepare_fixture"] = _try_prepare_skipped_fixture(
            container=args.backend_container.strip()
        )
        if not summary["prepare_fixture"].get("ok"):
            summary["overall_ok"] = False
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 1

    q_dry = urllib.parse.urlencode(
        _documents_query_params(limit=args.limit, only_mode=only_mode, dry_run=True)
    )
    url_dry = f"{base}/api/data-sources/{ds_id}/process-pending-documents?{q_dry}"
    st, payload, err = _api_request("POST", url_dry, token=token)
    block = _summarize_documents(payload if isinstance(payload, dict) else None)
    if err or st >= 400:
        block["ok"] = False
        block["error"] = err
        failed = True
    summary["dry_run"] = block

    dry_ok, dry_err, first_item = _validate_dry_run_target(block, only_mode=only_mode)
    summary["dry_run_validation"] = {"ok": dry_ok, "error": dry_err}
    if not dry_ok:
        failed = True
        if only_mode and (block.get("target_count") or 0) == 0:
            summary["hint"] = _FIXTURE_ZERO_HINT
    elif first_item:
        target_file_id = str(first_item.get("file_id") or "") or None
        summary["target_file_id"] = target_file_id

    if args.skip_run:
        summary["overall_ok"] = not failed
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1 if failed else 0

    if not dry_ok:
        summary["overall_ok"] = False
        summary["aborted"] = "dry_run validation failed"
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    if args.use_sync_api:
        q_run = urllib.parse.urlencode(
            _documents_query_params(limit=args.limit, only_mode=only_mode, dry_run=False)
        )
        url_run = f"{base}/api/data-sources/{ds_id}/process-pending-documents?{q_run}"
        st, payload, err = _api_request("POST", url_run, token=token, timeout=900)
        summary["documents_run"] = _summarize_documents(payload if isinstance(payload, dict) else None)
        if err or st >= 400:
            summary["documents_run"]["error"] = err
            failed = True
    else:
        body: dict[str, Any] = {
            "data_source_id": ds_id,
            "limit": max(1, args.limit),
            "reprocess_skipped": False,
            "priority": 0,
        }
        if only_mode:
            body["only_reprocess_hwp_no_extractable_text"] = True
        else:
            body["include_extensions"] = "hwp"
            body["reprocess_hwp_no_extractable_text"] = True

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
            jp = summary["job_poll"]
            if jp.get("status") != "COMPLETED":
                failed = True
            elif (jp.get("failed_files") or 0) > 0:
                failed = True
            summary["job_poll"]["expected_target_file_id"] = target_file_id

    if only_mode and target_file_id and not failed:
        q_after = urllib.parse.urlencode(
            _documents_query_params(limit=5, only_mode=True, dry_run=True)
        )
        st2, payload2, _ = _api_request(
            "POST",
            f"{base}/api/data-sources/{ds_id}/process-pending-documents?{q_after}",
            token=token,
        )
        after = _summarize_documents(payload2 if isinstance(payload, dict) else None)
        ids = [str(r.get("file_id")) for r in (after.get("items_preview") or [])]
        summary["post_dry_run"] = {
            "target_count": after.get("target_count"),
            "still_lists_target": target_file_id in ids,
        }
        if after.get("target_count", 0) > 0 and target_file_id in ids:
            failed = True
            summary["post_dry_run"]["error"] = "target still SKIPPED after job"

    q_chunk = urllib.parse.urlencode({"limit": "100", "include_extensions": "hwp"})
    st, payload, err = _api_request(
        "POST",
        f"{base}/api/data-sources/{ds_id}/chunk-completed-text?{q_chunk}",
        token=token,
    )
    summary["chunk"] = {
        "ok": st == 200 and not err,
        "created_chunks_count": (payload or {}).get("created_chunks_count")
        if isinstance(payload, dict)
        else None,
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
        "embedded_chunks_count": (payload or {}).get("embedded_chunks_count")
        if isinstance(payload, dict)
        else None,
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
    hit_target = False
    if isinstance(payload, dict):
        results = payload.get("results") or []
        if results and isinstance(results[0], dict):
            search_first = {
                "file_id": results[0].get("file_id"),
                "chunk_id": results[0].get("chunk_id"),
                "score": results[0].get("score"),
            }
        if target_file_id and isinstance(results, list):
            hit_target = any(
                isinstance(r, dict) and str(r.get("file_id")) == target_file_id for r in results
            )
    summary["search"] = {
        "ok": st == 200 and not err,
        "total_results": (payload or {}).get("total_results") if isinstance(payload, dict) else None,
        "first_result": search_first,
        "hit_target_file_id": hit_target if target_file_id else None,
    }
    if err or st >= 400:
        summary["search"]["error"] = err
        failed = True

    preview_fid = (search_first or {}).get("file_id")
    preview_cid = (search_first or {}).get("chunk_id")
    if preview_fid and preview_cid:
        q_prev = urllib.parse.urlencode(
            {"chunk_id": str(preview_cid), "context_lines": "5", "max_chars": "4000"}
        )
        st, payload, err = _api_request(
            "GET",
            f"{base}/api/files/{preview_fid}/preview?{q_prev}",
            token=token,
        )
        prev_block = _extract_preview_fields(payload if isinstance(payload, dict) else None)
        prev_block["ok"] = prev_block.get("ok") and st == 200 and not err
        if err or st >= 400:
            prev_block["error"] = err
            prev_block["ok"] = False
            failed = True
        summary["preview"] = prev_block

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
        hwp_citations = 0
        if isinstance(payload, dict):
            cites = payload.get("citations") or payload.get("sources") or []
            if isinstance(cites, list):
                citations = len(cites)
                for c in cites:
                    if not isinstance(c, dict):
                        continue
                    ext = str(c.get("extension") or "").lower()
                    if ext == "hwp":
                        hwp_citations += 1
                    if target_file_id and str(c.get("file_id")) == target_file_id:
                        summary.setdefault("answer", {})["cites_target_file"] = True
        summary["answer"] = {
            "ok": st == 200 and not err,
            "citations_count": citations,
            "hwp_citations_count": hwp_citations,
            "has_answer_text": bool((payload or {}).get("answer"))
            if isinstance(payload, dict)
            else False,
        }
        if err or st >= 400:
            summary["answer"]["error"] = err
            failed = True

    summary["overall_ok"] = not failed
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
