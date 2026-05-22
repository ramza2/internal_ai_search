#!/usr/bin/env python3
"""
HWP table/form extraction PoC — compare hwp5txt vs hwp5html (standalone; not imported by backend).

Does NOT modify HwpParser or process-pending-documents. Outputs under tmp/hwp_poc/ (gitignored).

Usage:
  python tools/hwp_poc/hwp_table_extraction_poc.py \\
    --input-dir tmp/hwp_poc/table_samples \\
    --output-dir tmp/hwp_poc/table_output \\
    --keywords "품목(문제)명,관리번호,에이전틱 AI"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

_STDERR_MAX = 1000
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_DIGIT_RE = re.compile(r"\d")
_TABLE_PLACEHOLDER_RE = re.compile(r"<\s*표\s*>", re.IGNORECASE)
_TABLE_BLOCK_RE = re.compile(r"^---\s*table\s+\d+\s*---\s*$", re.IGNORECASE)
_SAFE_STEM_RE = re.compile(r"[^a-zA-Z0-9._-]+")

# TODO: tune thresholds after real table/form samples (see docs/07_아키텍처/hwp_표양식_추출고도화_poc.md)
_MIN_MEANINGFUL_LEN = 50
_HTML_BETTER_RATIO = 2.0
_HIGH_PLACEHOLDER_RATIO = 0.3


class _HtmlFlattenParser(HTMLParser):
    """Flatten HTML to line-oriented plain text for search/RAG (stdlib only)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_table = False
        self._table_index = 0
        self._row_cells: list[str] = []
        self._current_cell: list[str] = []
        self._lines: list[str] = []
        self._table_count = 0

    @property
    def table_count(self) -> int:
        return self._table_count

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in ("script", "style"):
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if t == "table":
            self._flush_cell()
            self._flush_row()
            self._in_table = True
            self._table_index += 1
            self._table_count += 1
            self._lines.append(f"--- table {self._table_index} ---")
            return
        if t in ("tr",):
            self._flush_cell()
            self._flush_row()
            return
        if t in ("td", "th"):
            self._flush_cell()
            return
        if t in ("p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
            if not self._in_table:
                self._lines.append("")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("script", "style"):
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if t in ("td", "th"):
            self._flush_cell()
            return
        if t == "tr":
            self._flush_row()
            return
        if t == "table":
            self._flush_cell()
            self._flush_row()
            self._in_table = False
            self._lines.append("")
            return
        if t in ("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
            if not self._in_table:
                self._lines.append("")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        chunk = re.sub(r"\s+", " ", data)
        if not chunk.strip():
            return
        if self._in_table:
            self._current_cell.append(chunk.strip())
        else:
            self._lines.append(chunk.strip())

    def _flush_cell(self) -> None:
        if self._current_cell:
            self._row_cells.append(" ".join(self._current_cell).strip())
            self._current_cell = []

    def _flush_row(self) -> None:
        self._flush_cell()
        if self._row_cells:
            self._lines.append("\t".join(c for c in self._row_cells if c))
            self._row_cells = []

    def get_text(self) -> str:
        self._flush_cell()
        self._flush_row()
        normalized: list[str] = []
        for line in self._lines:
            s = re.sub(r"[ \t]+", " ", line).strip()
            if s:
                normalized.append(s)
        return "\n".join(normalized) + ("\n" if normalized else "")


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
    return len(text.splitlines()) if text else 0


def _korean_char_count(text: str) -> int:
    return len(_HANGUL_RE.findall(text))


def _meaningful_len(text: str) -> int:
    """Length after removing table placeholders and excess whitespace."""
    t = _TABLE_PLACEHOLDER_RE.sub("", text)
    t = re.sub(r"\s+", "", t)
    return len(t)


def _table_placeholder_count(text: str) -> int:
    return len(_TABLE_PLACEHOLDER_RE.findall(text))


def _keyword_hits(text: str, keywords: list[str]) -> dict[str, int]:
    lower = text.lower()
    return {kw: lower.count(kw.lower()) for kw in keywords if kw.strip()}


def _normalize_keyword(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def _keyword_hits_normalized(text: str, keywords: list[str]) -> dict[str, int]:
    norm_text = _normalize_keyword(text)
    return {_normalize_keyword(kw): norm_text.count(_normalize_keyword(kw)) for kw in keywords if kw.strip()}


def _analyze_flatten_table_blocks(flat: str) -> dict[str, int]:
    """
    Split flatten output on ``--- table N ---`` markers and sum in-block text.
    """
    lines = flat.splitlines()
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if _TABLE_BLOCK_RE.match(line.strip()):
            if current:
                blocks.append(current)
            current = []
            continue
        if line.strip():
            current.append(line.strip())
    if current:
        blocks.append(current)

    block_texts = ["\n".join(b) for b in blocks]
    total_text = "\n".join(block_texts)
    return {
        "html_table_block_count": len(blocks),
        "html_table_block_line_count": sum(len(b) for b in blocks),
        "html_table_block_text_size": len(total_text.encode("utf-8")),
        "html_table_text_estimate": _meaningful_len(total_text),
        "recovered_table_text_estimate": sum(len(line) for line in total_text.splitlines() if "\t" in line),
    }


def _decode_bytes(raw: bytes) -> tuple[str, str | None]:
    if not raw:
        return "", None
    for enc in ("utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(enc), None
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "decoded with utf-8 errors=replace"


def _resolve_bin(name: str) -> str | None:
    name = (name or "").strip()
    if not name:
        return None
    found = shutil.which(name)
    if found:
        return found
    p = Path(name)
    return str(p.resolve()) if p.is_file() else None


def _run_help(bin_path: str, timeout: float) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            [bin_path, "--help"],
            capture_output=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)[:200]
    out = (proc.stdout or proc.stderr or b"").decode("utf-8", errors="replace")
    summary = out.strip().replace("\n", " ")[:300]
    return proc.returncode == 0, summary or f"exit {proc.returncode}"


def _run_hwp5txt(
    *,
    bin_path: str,
    hwp_path: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    cmd = [bin_path, str(hwp_path.resolve())]
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout_seconds,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "elapsed_ms": int(timeout_seconds * 1000),
            "error": f"timeout after {timeout_seconds}s",
            "stderr_summary": f"timeout after {timeout_seconds}s",
        }
    except OSError as exc:
        return {
            "success": False,
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
            "error": f"{type(exc).__name__}: {exc}",
            "stderr_summary": str(exc)[:_STDERR_MAX],
        }
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    stderr = _stderr_summary(proc.stderr)
    if proc.returncode != 0:
        return {
            "success": False,
            "elapsed_ms": elapsed_ms,
            "returncode": proc.returncode,
            "error": stderr or f"exit {proc.returncode}",
            "stderr_summary": stderr,
        }
    text, note = _decode_bytes(proc.stdout or b"")
    if note:
        stderr = (stderr + "; " + note) if stderr else note
    return {
        "success": True,
        "elapsed_ms": elapsed_ms,
        "returncode": proc.returncode,
        "text": text,
        "stderr_summary": stderr,
    }


def _run_hwp5html(
    *,
    bin_path: str,
    hwp_path: Path,
    timeout_seconds: int,
    work_dir: Path,
) -> dict[str, Any]:
    """Run hwp5html defensively: --output file, else stdout capture."""
    stem = _sanitize_stem(hwp_path.name)
    out_html = work_dir / f"{stem}.html"
    help_ok, help_snippet = _run_help(bin_path, min(15.0, timeout_seconds))

    strategies: list[tuple[str, list[str]]] = [
        (
            "output_html",
            [bin_path, "--html", "--output", str(out_html), str(hwp_path.resolve())],
        ),
        (
            "output_no_flag",
            [bin_path, "--output", str(out_html), str(hwp_path.resolve())],
        ),
        (
            "stdout",
            [bin_path, "--html", str(hwp_path.resolve())],
        ),
    ]

    last_err: str | None = None
    for name, cmd in strategies:
        if name != "stdout" and out_html.exists():
            out_html.unlink(missing_ok=True)
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout_seconds,
                shell=False,
                check=False,
                cwd=str(work_dir) if name == "stdout" else None,
            )
        except subprocess.TimeoutExpired:
            last_err = f"{name}: timeout"
            continue
        except OSError as exc:
            last_err = f"{name}: {exc}"
            continue
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        stderr = _stderr_summary(proc.stderr)
        if proc.returncode != 0:
            last_err = stderr or f"{name}: exit {proc.returncode}"
            continue

        raw_html = b""
        if name == "stdout":
            raw_html = proc.stdout or b""
        elif out_html.is_file():
            raw_html = out_html.read_bytes()
        else:
            # Some versions write index.html beside output
            candidates = list(work_dir.glob("*.html")) + list(work_dir.glob("**/*.html"))
            if candidates:
                raw_html = candidates[0].read_bytes()
            else:
                last_err = f"{name}: no html output file"
                continue

        html_text, note = _decode_bytes(raw_html)
        if not html_text.strip():
            last_err = f"{name}: empty html"
            continue
        return {
            "success": True,
            "elapsed_ms": elapsed_ms,
            "strategy": name,
            "raw_html": html_text,
            "raw_size": len(html_text.encode("utf-8")),
            "help_ok": help_ok,
            "help_snippet": help_snippet,
            "stderr_summary": stderr,
            "decode_note": note,
        }

    return {
        "success": False,
        "error": last_err or "all hwp5html strategies failed",
        "help_ok": help_ok,
        "help_snippet": help_snippet,
        "stderr_summary": last_err,
    }


def flatten_html(html: str) -> tuple[str, int]:
    parser = _HtmlFlattenParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # Fallback: strip tags naively
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.I | re.S)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
        flat = "\n".join(ln for ln in lines if ln) + ("\n" if lines else "")
        return flat, 0
    return parser.get_text(), parser.table_count


def assess_quality(
    text: str,
    *,
    table_placeholder_count: int,
    table_count_html: int = 0,
) -> str:
    """
    FULL / PARTIAL / NONE for one extraction path.
    TODO: calibrate with labeled table/form samples.
    """
    meaningful = _meaningful_len(text)
    lines = _line_count(text)
    korean = _korean_char_count(text)
    placeholders = table_placeholder_count
    if meaningful < _MIN_MEANINGFUL_LEN:
        if table_count_html > 0 and korean >= 20:
            return "PARTIAL"
        return "NONE"
    if lines > 0 and placeholders / max(lines, 1) >= _HIGH_PLACEHOLDER_RATIO:
        if meaningful >= _MIN_MEANINGFUL_LEN and korean >= 30:
            return "PARTIAL"
        return "NONE"
    if meaningful >= _MIN_MEANINGFUL_LEN and (korean >= 30 or _DIGIT_RE.search(text)):
        return "FULL"
    return "PARTIAL"


def compare_recommendation(
    quality_txt: str,
    quality_html: str,
    meaningful_txt: int,
    meaningful_html: int,
) -> str:
    if quality_txt == "NONE" and quality_html == "NONE":
        return "NO_EXTRACTABLE_TEXT"
    if quality_html in ("FULL", "PARTIAL") and quality_txt == "NONE":
        return "PREFER_HWP5HTML"
    if quality_txt in ("FULL", "PARTIAL") and quality_html == "NONE":
        return "KEEP_HWP5TXT"
    if meaningful_html >= meaningful_txt * _HTML_BETTER_RATIO and quality_html != "NONE":
        return "HTML_BETTER"
    if quality_txt == "FULL" and quality_html == "FULL":
        return "TIERED_HTML_THEN_TXT"
    if quality_txt == "PARTIAL" or quality_html == "PARTIAL":
        return "PARTIAL_OK"
    return "REVIEW_MANUAL"


@dataclass
class FileReport:
    sample_alias: str
    filename: str
    file_size_bytes: int
    hwp5txt_success: bool = False
    hwp5txt_elapsed_ms: int = 0
    hwp5txt_text_size: int = 0
    hwp5txt_line_count: int = 0
    hwp5txt_sha256: str | None = None
    hwp5txt_table_placeholder_count: int = 0
    hwp5html_success: bool = False
    hwp5html_elapsed_ms: int = 0
    hwp5html_raw_size: int = 0
    hwp5html_flatten_text_size: int = 0
    hwp5html_flatten_line_count: int = 0
    hwp5html_table_count: int = 0
    hwp5html_sha256: str | None = None
    korean_char_count_txt: int = 0
    korean_char_count_html: int = 0
    keyword_hits_txt: dict[str, int] = field(default_factory=dict)
    keyword_hits_html: dict[str, int] = field(default_factory=dict)
    keyword_hits_txt_normalized: dict[str, int] = field(default_factory=dict)
    keyword_hits_html_normalized: dict[str, int] = field(default_factory=dict)
    html_table_block_count: int = 0
    html_table_block_line_count: int = 0
    html_table_block_text_size: int = 0
    html_table_text_estimate: int = 0
    quality_txt: str = "NONE"
    quality_html: str = "NONE"
    recommendation: str = "REVIEW_MANUAL"
    error_summary: str | None = None
    hwp5html_strategy: str | None = None
    recovered_table_text_estimate: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def process_file(
    hwp_path: Path,
    *,
    sample_alias: str,
    output_dir: Path,
    hwp5txt_bin: str,
    hwp5html_bin: str | None,
    timeout_seconds: int,
    keywords: list[str],
) -> FileReport:
    size = hwp_path.stat().st_size
    stem = _sanitize_stem(hwp_path.name)
    report = FileReport(
        sample_alias=sample_alias,
        filename=hwp_path.name,
        file_size_bytes=size,
    )
    errors: list[str] = []

    txt_path = output_dir / f"{stem}.hwp5txt.txt"
    html_raw_path = output_dir / f"{stem}.hwp5html.raw.html"
    flat_path = output_dir / f"{stem}.hwp5html.flatten.txt"

    txt_res = _run_hwp5txt(
        bin_path=hwp5txt_bin,
        hwp_path=hwp_path,
        timeout_seconds=timeout_seconds,
    )
    if txt_res.get("success"):
        text = txt_res.get("text") or ""
        txt_path.write_text(text, encoding="utf-8")
        report.hwp5txt_success = True
        report.hwp5txt_elapsed_ms = int(txt_res.get("elapsed_ms", 0))
        report.hwp5txt_text_size = len(text.encode("utf-8"))
        report.hwp5txt_line_count = _line_count(text)
        report.hwp5txt_sha256 = _sha256_text(text)
        report.hwp5txt_table_placeholder_count = _table_placeholder_count(text)
        report.korean_char_count_txt = _korean_char_count(text)
        report.keyword_hits_txt = _keyword_hits(text, keywords)
        report.keyword_hits_txt_normalized = _keyword_hits_normalized(text, keywords)
        report.quality_txt = assess_quality(
            text,
            table_placeholder_count=report.hwp5txt_table_placeholder_count,
        )
    else:
        errors.append(f"hwp5txt: {txt_res.get('error') or 'failed'}")

    if hwp5html_bin:
        with tempfile.TemporaryDirectory(prefix="hwp5html_") as tmp:
            html_res = _run_hwp5html(
                bin_path=hwp5html_bin,
                hwp_path=hwp_path,
                timeout_seconds=timeout_seconds,
                work_dir=Path(tmp),
            )
        if html_res.get("success"):
            raw = html_res.get("raw_html") or ""
            html_raw_path.write_text(raw, encoding="utf-8")
            flat, table_count = flatten_html(raw)
            flat_path.write_text(flat, encoding="utf-8")
            report.hwp5html_success = True
            report.hwp5html_elapsed_ms = int(html_res.get("elapsed_ms", 0))
            report.hwp5html_raw_size = int(html_res.get("raw_size", 0))
            report.hwp5html_flatten_text_size = len(flat.encode("utf-8"))
            report.hwp5html_flatten_line_count = _line_count(flat)
            report.hwp5html_table_count = table_count
            report.hwp5html_sha256 = _sha256_text(flat)
            report.hwp5html_strategy = html_res.get("strategy")
            report.korean_char_count_html = _korean_char_count(flat)
            report.keyword_hits_html = _keyword_hits(flat, keywords)
            report.keyword_hits_html_normalized = _keyword_hits_normalized(flat, keywords)
            block_stats = _analyze_flatten_table_blocks(flat)
            report.html_table_block_count = block_stats["html_table_block_count"]
            report.html_table_block_line_count = block_stats["html_table_block_line_count"]
            report.html_table_block_text_size = block_stats["html_table_block_text_size"]
            report.html_table_text_estimate = block_stats["html_table_text_estimate"]
            report.recovered_table_text_estimate = block_stats["recovered_table_text_estimate"]
            report.quality_html = assess_quality(
                flat,
                table_placeholder_count=_table_placeholder_count(flat),
                table_count_html=table_count,
            )
        else:
            err = html_res.get("error") or "failed"
            if not html_res.get("help_ok"):
                err = f"{err}; help: {html_res.get('help_snippet', '')[:120]}"
            errors.append(f"hwp5html: {err}")
    else:
        errors.append("hwp5html: binary not found on PATH")

    meaningful_txt = _meaningful_len(txt_path.read_text(encoding="utf-8")) if txt_path.is_file() else 0
    meaningful_html = (
        _meaningful_len(flat_path.read_text(encoding="utf-8")) if flat_path.is_file() else 0
    )
    report.recommendation = compare_recommendation(
        report.quality_txt,
        report.quality_html,
        meaningful_txt,
        meaningful_html,
    )
    if errors:
        report.error_summary = "; ".join(errors)[:_STDERR_MAX]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="HWP table/form extraction PoC: hwp5txt vs hwp5html"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("tmp/hwp_poc/table_samples"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tmp/hwp_poc/table_output"),
    )
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--hwp5txt-bin", default="hwp5txt")
    parser.add_argument("--hwp5html-bin", default="hwp5html")
    parser.add_argument(
        "--keywords",
        default="",
        help='Comma-separated keywords (e.g. "품목(문제)명,관리번호,에이전틱 AI"). '
        "Normalized hits also reported (whitespace-insensitive).",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to report JSONL instead of overwrite (default: overwrite)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON summary to stdout")
    args = parser.parse_args()

    input_dir: Path = args.input_dir
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.is_dir():
        print(f"[poc] input-dir not found: {input_dir}", file=sys.stderr)
        print("[poc] mkdir -p tmp/hwp_poc/table_samples and copy .hwp samples (do not commit)", file=sys.stderr)
        return 2

    hwp_files = sorted(input_dir.glob("*.hwp")) + sorted(input_dir.glob("*.HWP"))
    if not hwp_files:
        print(f"[poc] no .hwp files in {input_dir}", file=sys.stderr)
        return 2

    hwp5txt_bin = _resolve_bin(args.hwp5txt_bin)
    if not hwp5txt_bin:
        print(f"[poc] hwp5txt not found: {args.hwp5txt_bin!r}", file=sys.stderr)
        return 2
    hwp5html_bin = _resolve_bin(args.hwp5html_bin)

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    reports: list[FileReport] = []
    report_path = output_dir / "hwp_table_extraction_report.jsonl"

    for idx, hwp_path in enumerate(hwp_files, start=1):
        rep = process_file(
            hwp_path,
            sample_alias=f"sample{idx:02d}",
            output_dir=output_dir,
            hwp5txt_bin=hwp5txt_bin,
            hwp5html_bin=hwp5html_bin,
            timeout_seconds=args.timeout_seconds,
            keywords=keywords,
        )
        reports.append(rep)

    mode = "a" if args.append else "w"
    with report_path.open(mode, encoding="utf-8") as fh:
        for rep in reports:
            fh.write(json.dumps(rep.to_dict(), ensure_ascii=False) + "\n")

    summary = {
        "files": len(reports),
        "hwp5txt_ok": sum(1 for r in reports if r.hwp5txt_success),
        "hwp5html_ok": sum(1 for r in reports if r.hwp5html_success),
        "prefer_html": sum(1 for r in reports if "HTML" in r.recommendation),
        "none_both": sum(
            1 for r in reports if r.quality_txt == "NONE" and r.quality_html == "NONE"
        ),
        "report_path": str(report_path),
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"[poc] files={summary['files']} hwp5txt_ok={summary['hwp5txt_ok']} "
            f"hwp5html_ok={summary['hwp5html_ok']} prefer_html={summary['prefer_html']} "
            f"none_both={summary['none_both']} report_mode={'append' if args.append else 'overwrite'}"
        )
        print(f"[poc] report: {report_path}")
        for r in reports:
            err = ""
            if r.error_summary:
                err = f" err={r.error_summary[:60]}…" if len(r.error_summary) > 60 else f" err={r.error_summary}"
            print(
                f"  - {r.sample_alias}: txt={r.quality_txt} html={r.quality_html} "
                f"rec={r.recommendation} size {r.hwp5txt_text_size}B→{r.hwp5html_flatten_text_size}B "
                f"table_blocks={r.html_table_block_count} "
                f"table_text~{r.html_table_text_estimate}B{err}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
