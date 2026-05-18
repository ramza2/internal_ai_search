#!/usr/bin/env python3
"""
HWP runtime readiness check (standalone; not imported by backend).

Verifies hwp5txt availability and Python packages used by pyhwp/hwp5txt
without requiring a sample .hwp file.

Usage:
  python tools/hwp_poc/check_hwp_runtime.py
  python tools/hwp_poc/check_hwp_runtime.py --json
  python tools/hwp_poc/check_hwp_runtime.py --hwp5txt-bin /path/to/hwp5txt
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
    configured = (configured or "hwp5txt").strip()
    if not configured:
        return False, None, "empty hwp5txt bin name"
    found = shutil.which(configured)
    if found:
        return True, found, None
    if os.path.isfile(configured):
        return True, os.path.abspath(configured), None
    return False, None, f"not found on PATH: {configured!r}"


def _run_help(bin_path: str, timeout: float) -> tuple[bool, str | None]:
    try:
        proc = subprocess.run(
            [bin_path, "--help"],
            capture_output=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "hwp5txt --help timed out"
    except OSError as exc:
        return False, f"hwp5txt --help failed: {type(exc).__name__}"
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace").strip()
        summary = err[:200] + ("…" if len(err) > 200 else "")
        return False, summary or f"exit code {proc.returncode}"
    return True, None


def run_check(*, hwp5txt_bin: str, timeout_seconds: float) -> dict[str, Any]:
    imports = {name: _check_import(name) for name in _IMPORT_MODULES}
    found, resolved, resolve_err = _resolve_bin(hwp5txt_bin)
    help_ok = False
    help_err: str | None = None
    if found and resolved:
        help_ok, help_err = _run_help(resolved, timeout_seconds)

    env_snapshot = {
        "HWP5TXT_BIN": os.environ.get("HWP5TXT_BIN"),
        "HWP_PARSER_TIMEOUT_SECONDS": os.environ.get("HWP_PARSER_TIMEOUT_SECONDS"),
        "HWP_MIN_EXTRACTED_TEXT_LENGTH": os.environ.get("HWP_MIN_EXTRACTED_TEXT_LENGTH"),
    }

    ok = found and help_ok and all(imports.values())
    status = "ok" if ok else "fail"

    out: dict[str, Any] = {
        "status": status,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "hwp5txt_bin_configured": hwp5txt_bin,
        "hwp5txt_found": found,
        "hwp5txt_path": resolved,
        "hwp5txt_help_ok": help_ok,
        "imports": imports,
        "env": env_snapshot,
    }
    if resolve_err:
        out["hwp5txt_resolve_error"] = resolve_err
    if help_err:
        out["hwp5txt_help_error"] = help_err
    if not all(imports.values()):
        out["missing_imports"] = [k for k, v in imports.items() if not v]
    return out


def _print_human(report: dict[str, Any]) -> None:
    print(f"status: {report['status']}")
    print(f"python_version: {report['python_version']}")
    print(f"platform: {report['platform']}")
    print(f"hwp5txt_bin_configured: {report['hwp5txt_bin_configured']}")
    print(f"hwp5txt_found: {report['hwp5txt_found']}")
    if report.get("hwp5txt_path"):
        print(f"hwp5txt_path: {report['hwp5txt_path']}")
    print(f"hwp5txt_help_ok: {report['hwp5txt_help_ok']}")
    print("imports:")
    for name, ok in report["imports"].items():
        print(f"  {name}: {'ok' if ok else 'MISSING'}")
    env = report.get("env") or {}
    if any(env.values()):
        print("env (set only):")
        for k, v in env.items():
            if v is not None:
                print(f"  {k}={v}")
    for key in ("hwp5txt_resolve_error", "hwp5txt_help_error", "missing_imports"):
        if report.get(key):
            print(f"{key}: {report[key]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check HWP/hwp5txt runtime readiness")
    parser.add_argument(
        "--hwp5txt-bin",
        default=os.environ.get("HWP5TXT_BIN", "hwp5txt"),
        help="hwp5txt executable name or path (default: HWP5TXT_BIN env or hwp5txt)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=10.0,
        help="Timeout for hwp5txt --help (default: 10)",
    )
    args = parser.parse_args()
    report = run_check(
        hwp5txt_bin=args.hwp5txt_bin,
        timeout_seconds=max(1.0, args.timeout_seconds),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report)
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
