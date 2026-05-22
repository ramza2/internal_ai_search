#!/usr/bin/env python3
"""
HWP runtime readiness check (standalone; not imported by backend).

Verifies hwp5txt / hwp5html availability and Python packages used by pyhwp
without requiring a sample .hwp file.

Usage:
  python tools/hwp_poc/check_hwp_runtime.py
  python tools/hwp_poc/check_hwp_runtime.py --json
  python tools/hwp_poc/check_hwp_runtime.py --hwp5txt-bin /path/to/hwp5txt
  python tools/hwp_poc/check_hwp_runtime.py --hwp5html-bin /path/to/hwp5html
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
from typing import Any

_IMPORT_MODULES = ("hwp5", "six", "lxml", "olefile", "cryptography")


def _check_import(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


def _resolve_bin(configured: str) -> tuple[bool, str | None, str | None]:
    configured = (configured or "").strip()
    if not configured:
        return False, None, "empty bin name"
    found = shutil.which(configured)
    if found:
        return True, found, None
    if os.path.isfile(configured):
        return True, os.path.abspath(configured), None
    return False, None, f"not found on PATH: {configured!r}"


def _run_help(bin_path: str, timeout: float, label: str) -> tuple[bool, str | None]:
    try:
        proc = subprocess.run(
            [bin_path, "--help"],
            capture_output=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"{label} --help timed out"
    except OSError as exc:
        return False, f"{label} --help failed: {type(exc).__name__}"
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace").strip()
        summary = err[:200] + ("…" if len(err) > 200 else "")
        return False, summary or f"exit code {proc.returncode}"
    return True, None


def _normalize_strategy(raw: str | None) -> str:
    value = (raw or "tiered").strip().lower().replace("-", "_")
    if value in ("hwp5txt_only", "txt_only", "hwp5txt"):
        return "hwp5txt_only"
    if value in ("hwp5html_only", "html_only", "hwp5html"):
        return "hwp5html_only"
    return "tiered"


def run_check(
    *,
    hwp5txt_bin: str,
    hwp5html_bin: str,
    timeout_seconds: float,
    extraction_strategy: str | None = None,
) -> dict[str, Any]:
    strategy = _normalize_strategy(
        extraction_strategy or os.environ.get("HWP_EXTRACTION_STRATEGY")
    )
    imports = {name: _check_import(name) for name in _IMPORT_MODULES}
    txt_found, txt_path, txt_resolve_err = _resolve_bin(hwp5txt_bin)
    html_found, html_path, html_resolve_err = _resolve_bin(hwp5html_bin)
    txt_help_ok = False
    txt_help_err: str | None = None
    html_help_ok = False
    html_help_err: str | None = None
    if txt_found and txt_path:
        txt_help_ok, txt_help_err = _run_help(txt_path, timeout_seconds, "hwp5txt")
    if html_found and html_path:
        html_help_ok, html_help_err = _run_help(html_path, timeout_seconds, "hwp5html")

    env_snapshot = {
        "HWP_EXTRACTION_STRATEGY": os.environ.get("HWP_EXTRACTION_STRATEGY"),
        "HWP5TXT_BIN": os.environ.get("HWP5TXT_BIN"),
        "HWP5HTML_BIN": os.environ.get("HWP5HTML_BIN"),
        "HWP_PARSER_TIMEOUT_SECONDS": os.environ.get("HWP_PARSER_TIMEOUT_SECONDS"),
        "HWP_MIN_EXTRACTED_TEXT_LENGTH": os.environ.get("HWP_MIN_EXTRACTED_TEXT_LENGTH"),
        "HWP_HTML_MIN_EXTRACTED_TEXT_LENGTH": os.environ.get(
            "HWP_HTML_MIN_EXTRACTED_TEXT_LENGTH"
        ),
    }

    needs_txt = strategy in ("hwp5txt_only", "tiered")
    needs_html = strategy in ("hwp5html_only", "tiered")
    txt_ok = (not needs_txt) or (txt_found and txt_help_ok)
    html_ok = (not needs_html) or (html_found and html_help_ok)
    ok = txt_ok and html_ok and all(imports.values())
    status = "ok" if ok else "fail"

    out: dict[str, Any] = {
        "status": status,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "hwp_extraction_strategy": strategy,
        "hwp5txt_bin_configured": hwp5txt_bin,
        "hwp5txt_found": txt_found,
        "hwp5txt_path": txt_path,
        "hwp5txt_help_ok": txt_help_ok,
        "hwp5html_bin_configured": hwp5html_bin,
        "hwp5html_found": html_found,
        "hwp5html_path": html_path,
        "hwp5html_help_ok": html_help_ok,
        "imports": imports,
        "env": env_snapshot,
        "strategy_requires": {
            "hwp5txt": needs_txt,
            "hwp5html": needs_html,
        },
    }
    if txt_resolve_err:
        out["hwp5txt_resolve_error"] = txt_resolve_err
    if txt_help_err:
        out["hwp5txt_help_error"] = txt_help_err
    if html_resolve_err:
        out["hwp5html_resolve_error"] = html_resolve_err
    if html_help_err:
        out["hwp5html_help_error"] = html_help_err
    if not all(imports.values()):
        out["missing_imports"] = [k for k, v in imports.items() if not v]
    if strategy == "tiered" and not html_found:
        out["note"] = "tiered strategy: hwp5txt fallback remains if hwp5html is missing"
    return out


def _print_human(report: dict[str, Any]) -> None:
    print(f"status: {report['status']}")
    print(f"python_version: {report['python_version']}")
    print(f"platform: {report['platform']}")
    print(f"hwp_extraction_strategy: {report['hwp_extraction_strategy']}")
    req = report.get("strategy_requires") or {}
    print(f"requires hwp5txt: {req.get('hwp5txt')}")
    print(f"requires hwp5html: {req.get('hwp5html')}")
    print(f"hwp5txt_found: {report['hwp5txt_found']}")
    if report.get("hwp5txt_path"):
        print(f"hwp5txt_path: {report['hwp5txt_path']}")
    print(f"hwp5txt_help_ok: {report['hwp5txt_help_ok']}")
    print(f"hwp5html_found: {report['hwp5html_found']}")
    if report.get("hwp5html_path"):
        print(f"hwp5html_path: {report['hwp5html_path']}")
    print(f"hwp5html_help_ok: {report['hwp5html_help_ok']}")
    print("imports:")
    for name, ok in report["imports"].items():
        print(f"  {name}: {'ok' if ok else 'MISSING'}")
    env = report.get("env") or {}
    if any(env.values()):
        print("env (set only):")
        for k, v in env.items():
            if v is not None:
                print(f"  {k}={v}")
    for key in (
        "hwp5txt_resolve_error",
        "hwp5txt_help_error",
        "hwp5html_resolve_error",
        "hwp5html_help_error",
        "missing_imports",
        "note",
    ):
        if report.get(key):
            print(f"{key}: {report[key]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check HWP/hwp5txt/hwp5html runtime readiness")
    parser.add_argument(
        "--hwp5txt-bin",
        default=os.environ.get("HWP5TXT_BIN", "hwp5txt"),
        help="hwp5txt executable (default: HWP5TXT_BIN or hwp5txt)",
    )
    parser.add_argument(
        "--hwp5html-bin",
        default=os.environ.get("HWP5HTML_BIN", "hwp5html"),
        help="hwp5html executable (default: HWP5HTML_BIN or hwp5html)",
    )
    parser.add_argument(
        "--strategy",
        default=os.environ.get("HWP_EXTRACTION_STRATEGY", "tiered"),
        help="HWP_EXTRACTION_STRATEGY (tiered | hwp5txt_only | hwp5html_only)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=10.0,
        help="Timeout for CLI --help (default: 10)",
    )
    args = parser.parse_args()
    report = run_check(
        hwp5txt_bin=args.hwp5txt_bin,
        hwp5html_bin=args.hwp5html_bin,
        timeout_seconds=max(1.0, args.timeout_seconds),
        extraction_strategy=args.strategy,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report)
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
