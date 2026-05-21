#!/usr/bin/env python3
"""
Diagnose one .hwp or .hwpx file using the same rules as the backend.

Place your file under tmp/hwp_poc/samples/ (gitignored) and run from backend venv:

  cd backend
  .\\.venv\\Scripts\\Activate.ps1
  python ..\\tools\\hwp_poc\\diagnose_hwp_file.py ..\\tmp\\hwp_poc\\samples\\doc.hwp
  python ..\\tools\\hwp_poc\\diagnose_hwp_file.py ..\\tmp\\hwp_poc\\samples\\doc.hwpx --preview-chars 400

Optional: --preview-chars 400  --json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import zipfile
from io import BytesIO
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_MIN_MEANINGFUL_ORCHESTRATOR = 5
_SUPPORTED_SUFFIXES = {".hwp", ".hwpx"}


def _stripped_length(text: str) -> int:
    return len("".join((text or "").split()))


def _meaningful_orchestrator(text: str | None) -> bool:
    return _stripped_length(text or "") >= _MIN_MEANINGFUL_ORCHESTRATOR


def _decode_stdout(raw: bytes) -> tuple[str, str | None]:
    if not raw:
        return "", None
    for enc in ("utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(enc), None
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8 errors=replace"


def _finalize_document_status(
    *,
    result,
    min_length_hwp: int | None,
) -> tuple[str, str | None]:
    """Mirror pending_document_processor decisions after parse_bytes."""
    text = result.extracted_text or ""
    code = (result.error_code or "").strip().upper() if result.error_code else ""

    if not result.success:
        if code == "NO_EXTRACTABLE_TEXT":
            return "SKIPPED (parser min length)", "NO_EXTRACTABLE_TEXT"
        return f"FAILED/SKIPPED ({result.error_code or 'PARSING_FAILED'})", result.error_code

    if not _meaningful_orchestrator(text):
        return "SKIPPED (orchestrator _meaningful_text)", "NO_EXTRACTABLE_TEXT"

    return "COMPLETED (would save file_contents)", None


def _run_hwp5txt_raw(bin_path: str, hwp_path: Path, timeout: int) -> dict:
    cmd = [bin_path, str(hwp_path.resolve())]
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "stage": "hwp5txt_subprocess",
            "error": f"timeout after {timeout}s",
            "stderr": (exc.stderr or b"").decode("utf-8", errors="replace")[:500],
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        }
    except OSError as exc:
        return {
            "ok": False,
            "stage": "hwp5txt_subprocess",
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        }

    text, decode_note = _decode_stdout(proc.stdout or b"")
    stderr = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
    return {
        "ok": proc.returncode == 0,
        "stage": "hwp5txt_subprocess",
        "returncode": proc.returncode,
        "stderr": stderr[:1000] if stderr else None,
        "decode_note": decode_note,
        "raw_char_count": len(text),
        "stripped_char_count": _stripped_length(text),
        "line_count": len(text.splitlines()) if text else 0,
        "contains_korean": bool(_HANGUL_RE.search(text)),
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        "text_preview": text[:400] if text else "",
    }


def _inspect_hwpx_zip(content: bytes) -> dict:
    """Lightweight zip layout check (no full parse)."""
    try:
        zf = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as exc:
        return {"ok": False, "error": f"BadZipFile: {exc}"}

    names = zf.namelist()
    xml_names = [n for n in names if n.lower().endswith(".xml")]
    zf.close()
    return {
        "ok": True,
        "member_count": len(names),
        "xml_count": len(xml_names),
        "sample_xml": xml_names[:8],
    }


def _backend_parser_result(doc_path: Path, ext: str) -> dict:
    from app.core.config import settings

    body = doc_path.read_bytes()
    min_len_hwp = int(settings.hwp_min_extracted_text_length)

    if ext == ".hwp":
        from app.parsers.hwp_parser import HwpParser

        parser = HwpParser()
        result = parser.parse_bytes(body, doc_path.name, "hwp")
        min_note = min_len_hwp
    elif ext == ".hwpx":
        from app.parsers.hwpx_parser import HwpxParser

        parser = HwpxParser()
        result = parser.parse_bytes(body, doc_path.name, "hwpx")
        min_note = None  # HWPX has no hwp5txt min-length gate inside parser
    else:
        raise ValueError(ext)

    text = result.extracted_text or ""
    final_status, final_code = _finalize_document_status(
        result=result,
        min_length_hwp=min_len_hwp if ext == ".hwp" else None,
    )

    out = {
        "format": ext.lstrip("."),
        "parser_success": result.success,
        "parser_error_code": result.error_code,
        "parser_error_message": result.error_message,
        "parser_name": result.parser_name,
        "parser_version": result.parser_version,
        "hwp_min_extracted_text_length": min_note,
        "stripped_char_count": _stripped_length(text),
        "raw_char_count": len(text),
        "orchestrator_min_stripped": _MIN_MEANINGFUL_ORCHESTRATOR,
        "orchestrator_meaningful": _meaningful_orchestrator(text),
        "final_status": final_status,
        "final_error_code": final_code,
        "metadata": dict(result.metadata) if result.metadata else {},
        "text_preview": text[:400] if text else "",
    }
    if ext == ".hwpx" and not result.success and _stripped_length(text) < _MIN_MEANINGFUL_ORCHESTRATOR:
        out["note"] = (
            "HwpxParser returned success=False; empty HWPX may still need orchestrator check."
        )
    return out


def diagnose(doc_path: Path, *, hwp5txt_bin: str | None, timeout: int) -> dict:
    if not doc_path.is_file():
        raise FileNotFoundError(doc_path)
    ext = doc_path.suffix.lower()
    if ext not in _SUPPORTED_SUFFIXES:
        raise ValueError(
            f"Unsupported extension {ext!r}; use .hwp or .hwpx: {doc_path}"
        )

    out: dict = {
        "file": str(doc_path.resolve()),
        "format": ext.lstrip("."),
        "file_size_bytes": doc_path.stat().st_size,
    }

    if ext == ".hwpx":
        out["hwpx_zip"] = _inspect_hwpx_zip(doc_path.read_bytes())
        out["hwp5txt_raw"] = None
        out["hwp5txt_bin_resolved"] = None
        out["note"] = "HWPX uses HwpxParser (ZIP/XML); hwp5txt is not used."
        out["backend_parser"] = _backend_parser_result(doc_path, ext)
        out["runtime_ok"] = True
        return out

    configured = hwp5txt_bin
    if not configured:
        try:
            from app.core.config import settings

            configured = settings.hwp5txt_bin
        except Exception:
            configured = "hwp5txt"

    bin_resolved = shutil.which(str(configured).strip()) or (
        str(configured) if Path(str(configured)).is_file() else None
    )
    out["hwp5txt_bin_configured"] = configured
    out["hwp5txt_bin_resolved"] = bin_resolved

    if not bin_resolved:
        out["runtime_ok"] = False
        out["error"] = "hwp5txt not found; pip install pyhwp or set HWP5TXT_BIN"
        return out

    out["hwp5txt_raw"] = _run_hwp5txt_raw(bin_resolved, doc_path, timeout)
    out["backend_parser"] = _backend_parser_result(doc_path, ext)
    out["runtime_ok"] = True
    return out


def _print_human(report: dict, *, show_preview: int) -> None:
    fmt = report.get("format", "?")
    print(f"=== {fmt.upper()} diagnose (backend rules) ===")
    print(f"file: {report.get('file')}")
    print(f"size: {report.get('file_size_bytes')} bytes")
    if report.get("note"):
        print(f"note: {report.get('note')}")

    if not report.get("runtime_ok"):
        print(f"\n[FAIL] {report.get('error')}")
        return

    if fmt == "hwpx":
        zx = report.get("hwpx_zip") or {}
        print("\n--- Step 1: HWPX zip layout ---")
        print(f"  ok: {zx.get('ok')}")
        print(f"  members: {zx.get('member_count')}")
        print(f"  xml files: {zx.get('xml_count')}")
        if zx.get("sample_xml"):
            print(f"  sample: {zx.get('sample_xml')}")
        if zx.get("error"):
            print(f"  error: {zx.get('error')}")
    else:
        print(f"hwp5txt: {report.get('hwp5txt_bin_resolved')}")
        raw = report.get("hwp5txt_raw") or {}
        print("\n--- Step 1: hwp5txt (subprocess) ---")
        print(f"  returncode: {raw.get('returncode')}")
        print(f"  ok: {raw.get('ok')}")
        print(f"  stripped chars: {raw.get('stripped_char_count')}")
        print(f"  lines: {raw.get('line_count')}")
        print(f"  korean: {raw.get('contains_korean')}")
        if raw.get("stderr"):
            print(f"  stderr: {raw.get('stderr')[:300]}")
        if raw.get("error"):
            print(f"  error: {raw.get('error')}")

    bp = report.get("backend_parser") or {}
    step2 = "HwpxParser" if fmt == "hwpx" else "HwpParser"
    print(f"\n--- Step 2: backend {step2} + document processor rules ---")
    print(f"  parser_success: {bp.get('parser_success')}")
    print(f"  parser_error_code: {bp.get('parser_error_code')}")
    print(f"  parser_error_message: {bp.get('parser_error_message')}")
    if bp.get("hwp_min_extracted_text_length") is not None:
        print(
            f"  min_length (HWP_MIN_EXTRACTED_TEXT_LENGTH): "
            f"{bp.get('hwp_min_extracted_text_length')}"
        )
    print(f"  stripped chars after parse: {bp.get('stripped_char_count')}")
    print(f"  orchestrator min stripped: {bp.get('orchestrator_min_stripped')}")
    print(f"  >>> final: {bp.get('final_status')}")
    if bp.get("final_error_code"):
        print(f"  >>> error_code in DB/scan_failures: {bp.get('final_error_code')}")

    if show_preview > 0:
        raw = report.get("hwp5txt_raw") or {}
        prev = (bp.get("text_preview") or raw.get("text_preview") or "")[:show_preview]
        if prev:
            print(f"\n--- text preview (first {show_preview} chars) ---")
            print(prev)
        else:
            print("\n--- text preview: (empty) ---")

    if fmt == "hwp":
        print("\nTip: low stripped chars + <표> placeholders → hwp5txt table limit.")
        print("     Try the same document as .hwpx (HwpxParser).")
    else:
        print("\nTip: if stripped chars is high but search still misses content,")
        print("     check pipeline steps (COMPLETED → chunk → embed).")


def _pick_default_sample(sample_dir: Path, suffix: str) -> Path | None:
    candidates = sorted(sample_dir.glob(f"*{suffix}"))
    if len(candidates) == 1:
        return candidates[0]
    return None


def main() -> int:
    default_sample = _REPO_ROOT / "tmp" / "hwp_poc" / "samples"
    ap = argparse.ArgumentParser(
        description="Diagnose one .hwp or .hwpx like the backend does."
    )
    ap.add_argument(
        "doc_file",
        nargs="?",
        type=Path,
        help=f"Path to .hwp / .hwpx (default: single file in {default_sample})",
    )
    ap.add_argument("--hwp5txt-bin", default=None)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--preview-chars", type=int, default=0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    doc_path = args.doc_file
    if doc_path is None:
        if not default_sample.is_dir():
            default_sample.mkdir(parents=True, exist_ok=True)
        all_cands = sorted(
            p
            for p in default_sample.iterdir()
            if p.is_file() and p.suffix.lower() in _SUPPORTED_SUFFIXES
        )
        if len(all_cands) == 1:
            doc_path = all_cands[0]
        elif not all_cands:
            print(
                f"Put a .hwp or .hwpx under {default_sample} or pass a path.\n"
                "Example:\n"
                "  python tools/hwp_poc/diagnose_hwp_file.py "
                "tmp/hwp_poc/samples/doc.hwpx --preview-chars 400",
                file=sys.stderr,
            )
            return 2
        else:
            print("Multiple files found; specify one:", file=sys.stderr)
            for p in all_cands:
                print(f"  {p}", file=sys.stderr)
            return 2

    try:
        report = diagnose(doc_path, hwp5txt_bin=args.hwp5txt_bin, timeout=args.timeout)
    except Exception as exc:
        print(f"diagnose failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        if args.preview_chars <= 0:
            r = dict(report)

            def _strip_preview(d: dict | None) -> dict | None:
                if not isinstance(d, dict):
                    return d
                return {k: v for k, v in d.items() if k != "text_preview"}

            r["hwp5txt_raw"] = _strip_preview(r.get("hwp5txt_raw"))
            r["backend_parser"] = _strip_preview(r.get("backend_parser"))
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report, show_preview=max(0, args.preview_chars))

    bp = report.get("backend_parser") or {}
    if bp.get("final_error_code") == "NO_EXTRACTABLE_TEXT":
        return 3
    if not bp.get("parser_success") and bp.get("final_status", "").startswith("FAILED"):
        return 4
    if "COMPLETED" not in str(bp.get("final_status") or ""):
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
