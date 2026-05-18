#!/usr/bin/env python3
"""
Standalone HWP → TXT PoC runner (experimental).

NOT imported by backend. Install pyhwp only in a PoC venv:
  pip install pyhwp

Requires ``hwp5txt`` on PATH (from pyhwp package).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

_STDERR_MAX = 500
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_SAFE_STEM_RE = re.compile(r"[^a-zA-Z0-9._-]+")


@dataclass
class RunRecord:
    filename: str
    file_size_bytes: int
    run_index: int
    conversion_success: bool
    elapsed_ms: int
    returncode: int
    output_path: str | None
    output_text_size: int
    line_count: int
    sha256_of_output_text: str | None
    first_5_lines: list[str] = field(default_factory=list)
    contains_korean_ok: bool | None = None
    table_quality_note: str = "manual_review_required"
    error_message: str | None = None
    stderr_summary: str | None = None


@dataclass
class FileSummary:
    filename: str
    file_size_bytes: int
    runs: list[RunRecord] = field(default_factory=list)
    stable_line_count: bool | None = None
    stable_output_hash: bool | None = None


def _sanitize_stem(name: str) -> str:
    stem = Path(name).stem
    cleaned = _SAFE_STEM_RE.sub("_", stem).strip("._")
    return cleaned or "unnamed"


def _stderr_summary(stderr: bytes | str | None) -> str | None:
    if not stderr:
        return None
    text = stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else stderr
    text = text.strip()
    if not text:
        return None
    if len(text) > _STDERR_MAX:
        return text[:_STDERR_MAX] + "…(truncated)"
    return text


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _line_count(text: str) -> int:
    if not text:
        return 0
    return len(text.splitlines())


def _contains_korean(text: str) -> bool:
    return bool(_HANGUL_RE.search(text))


def _first_n_lines(text: str, n: int = 5) -> list[str]:
    lines: list[str] = []
    for i, line in enumerate(text.splitlines()):
        if i >= n:
            break
        # Avoid logging very long single lines in the report.
        s = line.strip()
        if len(s) > 200:
            s = s[:200] + "…"
        lines.append(s)
    return lines


def _resolve_hwp5txt(bin_name: str) -> Path | None:
    found = shutil.which(bin_name)
    return Path(found) if found else None


def _run_hwp5txt(
    *,
    hwp5txt_bin: str,
    hwp_path: Path,
    timeout_seconds: int,
) -> tuple[int, bytes, bytes, int]:
    """Invoke hwp5txt with stdout capture (shell=False)."""
    cmd = [hwp5txt_bin, str(hwp_path.resolve())]
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout_seconds,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        err = _stderr_summary(stderr) or f"timeout after {timeout_seconds}s"
        raise TimeoutError(err) from exc
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return proc.returncode, proc.stdout or b"", proc.stderr or b"", elapsed_ms


def _decode_stdout(raw: bytes) -> tuple[str | None, str | None]:
    if not raw:
        return "", None
    for enc in ("utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(enc), None
        except UnicodeDecodeError:
            continue
    text = raw.decode("utf-8", errors="replace")
    return text, "stdout decoded with utf-8 errors=replace"


def _process_one_run(
    *,
    hwp_path: Path,
    run_index: int,
    output_dir: Path,
    hwp5txt_bin: str,
    timeout_seconds: int,
) -> RunRecord:
    size = hwp_path.stat().st_size
    stem = _sanitize_stem(hwp_path.name)
    out_path = output_dir / f"{stem}__run{run_index}.txt"

    record = RunRecord(
        filename=hwp_path.name,
        file_size_bytes=size,
        run_index=run_index,
        conversion_success=False,
        elapsed_ms=0,
        returncode=-1,
        output_path=str(out_path),
        output_text_size=0,
        line_count=0,
        sha256_of_output_text=None,
    )

    try:
        returncode, stdout_raw, stderr_raw, elapsed_ms = _run_hwp5txt(
            hwp5txt_bin=hwp5txt_bin,
            hwp_path=hwp_path,
            timeout_seconds=timeout_seconds,
        )
    except TimeoutError as exc:
        record.elapsed_ms = int(timeout_seconds * 1000)
        record.error_message = str(exc)
        record.stderr_summary = str(exc)
        return record
    except OSError as exc:
        record.error_message = f"{type(exc).__name__}: {exc}"
        record.stderr_summary = record.error_message
        return record

    record.elapsed_ms = elapsed_ms
    record.returncode = returncode
    record.stderr_summary = _stderr_summary(stderr_raw)

    if returncode != 0:
        record.error_message = (
            record.stderr_summary
            or f"hwp5txt exited with code {returncode}"
        )
        return record

    text, decode_note = _decode_stdout(stdout_raw)
    if decode_note:
        record.error_message = decode_note

    if text is None:
        text = ""

    out_path.write_text(text, encoding="utf-8")
    record.output_text_size = len(text.encode("utf-8"))
    record.line_count = _line_count(text)
    record.sha256_of_output_text = _sha256_text(text)
    record.first_5_lines = _first_n_lines(text, 5)
    record.contains_korean_ok = _contains_korean(text)
    record.conversion_success = record.line_count > 0 or bool(text.strip())

    if not record.conversion_success:
        record.error_message = record.error_message or "empty output"

    return record


def _compare_stability(runs: list[RunRecord]) -> tuple[bool | None, bool | None]:
    if len(runs) < 2:
        return None, None
    ok = [r for r in runs if r.conversion_success]
    if len(ok) < 2:
        return None, None
    lines = [r.line_count for r in ok[:2]]
    hashes = [r.sha256_of_output_text for r in ok[:2]]
    stable_lines = lines[0] == lines[1]
    stable_hash = hashes[0] == hashes[1] and hashes[0] is not None
    return stable_lines, stable_hash


def _find_hwp_files(input_dir: Path) -> list[Path]:
    if not input_dir.is_dir():
        return []
    files = sorted(input_dir.glob("*.hwp")) + sorted(input_dir.glob("*.HWP"))
    # Deduplicate case-insensitive duplicates on Windows.
    seen: set[str] = set()
    unique: list[Path] = []
    for p in files:
        key = p.name.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def _print_summary(
    summaries: list[FileSummary], report_path: Path, output_dir: Path
) -> None:
    total = len(summaries)
    ok_files = sum(1 for s in summaries if any(r.conversion_success for r in s.runs))
    stable = sum(1 for s in summaries if s.stable_output_hash is True)
    report_abs = report_path.resolve()
    print(f"HWP PoC finished: files={total} with_success={ok_files} stable_hash_pairs={stable}")
    print(f"Report (JSONL): {report_abs}")
    print(f"TXT outputs: {output_dir.resolve()}")
    for s in summaries:
        last = s.runs[-1] if s.runs else None
        status = "OK" if last and last.conversion_success else "FAIL"
        line_info = f"lines={last.line_count}" if last else "lines=?"
        stab = ""
        if s.stable_line_count is not None:
            stab = f" stable_lines={s.stable_line_count} stable_hash={s.stable_output_hash}"
        print(f"  [{status}] {s.filename} ({s.file_size_bytes} B) {line_info}{stab}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run hwp5txt on sample .hwp files and write JSONL PoC report."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("tmp/hwp_poc/samples"),
        help="Directory containing .hwp sample files (default: tmp/hwp_poc/samples)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tmp/hwp_poc/output"),
        help="Directory for TXT outputs and report (default: tmp/hwp_poc/output)",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Per-file hwp5txt timeout (default: 120)",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=2,
        help="Conversion runs per file for stability check (default: 2)",
    )
    parser.add_argument(
        "--hwp5txt-bin",
        type=str,
        default="hwp5txt",
        help="hwp5txt executable name or path (default: hwp5txt)",
    )
    args = parser.parse_args(argv)

    if args.repeat < 1:
        print("error: --repeat must be >= 1", file=sys.stderr)
        return 2

    hwp5txt_path = _resolve_hwp5txt(args.hwp5txt_bin)
    if hwp5txt_path is None:
        print(
            "error: hwp5txt not found on PATH.\n"
            "  Install in a PoC-only venv: pip install pyhwp\n"
            "  Then verify: hwp5txt --help\n"
            f"  Or pass --hwp5txt-bin /path/to/hwp5txt\n"
            "  Windows dev PC: run PoC inside WSL2 (see "
            "docs/07_아키텍처/hwp_poc_windows_wsl_가이드.md)",
            file=sys.stderr,
        )
        return 1

    input_dir = args.input_dir
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    hwp_files = _find_hwp_files(input_dir)
    if not hwp_files:
        print(
            f"error: no .hwp files under {input_dir.resolve()}\n"
            "  mkdir -p tmp/hwp_poc/samples && copy sample .hwp files there",
            file=sys.stderr,
        )
        return 1

    report_path = output_dir / "hwp_poc_report.jsonl"
    summaries: list[FileSummary] = []

    with report_path.open("w", encoding="utf-8") as report_fp:
        for hwp_path in hwp_files:
            file_summary = FileSummary(
                filename=hwp_path.name,
                file_size_bytes=hwp_path.stat().st_size,
            )
            for run_index in range(1, args.repeat + 1):
                record = _process_one_run(
                    hwp_path=hwp_path,
                    run_index=run_index,
                    output_dir=output_dir,
                    hwp5txt_bin=str(hwp5txt_path),
                    timeout_seconds=args.timeout_seconds,
                )
                file_summary.runs.append(record)
                report_fp.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

            sl, sh = _compare_stability(file_summary.runs)
            file_summary.stable_line_count = sl
            file_summary.stable_output_hash = sh
            summaries.append(file_summary)

            summary_row = {
                "type": "file_summary",
                "filename": file_summary.filename,
                "file_size_bytes": file_summary.file_size_bytes,
                "stable_line_count": sl,
                "stable_output_hash": sh,
                "runs": len(file_summary.runs),
            }
            report_fp.write(json.dumps(summary_row, ensure_ascii=False) + "\n")

    _print_summary(summaries, report_path, output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
