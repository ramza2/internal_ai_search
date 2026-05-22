"""HWP binary (.hwp) extraction via hwp5txt / hwp5html CLI (no Automation/COM)."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.core.config import settings
from app.parsers.base import DocumentParser, ParserResult
from app.parsers.hwp_html_flattener import HwpHtmlFlattenResult, flatten_hwp_html
from app.parsers.hwp_quality import (
    QualityGrade,
    assess_extraction_quality,
    is_html_path_sufficient,
    is_txt_path_sufficient,
    korean_char_count,
    line_count,
    table_placeholder_count,
)
from app.services.text_extraction_service import normalize_extension

_STDERR_MAX = 1000
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")

ERR_CONVERTER_NOT_AVAILABLE = "HWP_CONVERTER_NOT_AVAILABLE"
ERR_CONVERSION_FAILED = "HWP_CONVERSION_FAILED"
ERR_CONVERSION_TIMEOUT = "HWP_CONVERSION_TIMEOUT"
ERR_NO_EXTRACTABLE_TEXT = "NO_EXTRACTABLE_TEXT"
ERR_PASSWORD_PROTECTED = "PASSWORD_PROTECTED"

CONVERTER_TXT = "hwp5txt"
CONVERTER_HTML = "hwp5html"
PARSER_NAME = "hwp_parser"

ExtractionStrategy = Literal["hwp5txt_only", "hwp5html_only", "tiered"]


def normalize_hwp_extraction_strategy(raw: str | None) -> ExtractionStrategy:
    value = (raw or "tiered").strip().lower().replace("-", "_")
    if value in ("hwp5txt_only", "txt_only", "hwp5txt"):
        return "hwp5txt_only"
    if value in ("hwp5html_only", "html_only", "hwp5html"):
        return "hwp5html_only"
    return "tiered"


@dataclass
class _TxtRunResult:
    success: bool
    text: str = ""
    stderr_summary: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    decode_note: str | None = None
    parser_version: str = "unknown"


@dataclass
class _HtmlRunResult:
    success: bool
    flatten: HwpHtmlFlattenResult | None = None
    stderr_summary: str | None = None
    error_summary: str | None = None
    strategy: str | None = None
    parser_version: str = "unknown"


def _truncate_stderr(stderr: bytes | str | None) -> str | None:
    if not stderr:
        return None
    text = stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else stderr
    text = text.strip()
    if not text:
        return None
    if len(text) > _STDERR_MAX:
        return text[:_STDERR_MAX] + "…(truncated)"
    return text


def _resolve_cli_bin(configured: str) -> str | None:
    configured = (configured or "").strip()
    if not configured:
        return None
    found = shutil.which(configured)
    if found:
        return found
    path = Path(configured)
    if path.is_file():
        return str(path.resolve())
    return None


def _resolve_hwp5txt_bin() -> str | None:
    return _resolve_cli_bin(settings.hwp5txt_bin or "hwp5txt")


def _resolve_hwp5html_bin() -> str | None:
    return _resolve_cli_bin(settings.hwp5html_bin or "hwp5html")


def _decode_stdout(raw: bytes) -> tuple[str, str | None]:
    if not raw:
        return "", None
    for enc in ("utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(enc), None
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "stdout decoded with utf-8 errors=replace"


def _decode_file_bytes(raw: bytes) -> tuple[str, str | None]:
    return _decode_stdout(raw)


def _normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _converter_version(bin_path: str) -> str:
    try:
        proc = subprocess.run(
            [bin_path, "--version"],
            capture_output=True,
            timeout=10,
            shell=False,
            check=False,
        )
        out = (proc.stdout or proc.stderr or b"").decode("utf-8", errors="replace").strip()
        if out:
            return out.splitlines()[0][:120]
    except Exception:
        pass
    return "unknown"


def _base_metadata(strategy: ExtractionStrategy) -> dict[str, Any]:
    return {
        "source_format": "hwp",
        "extraction_strategy": strategy,
        "fallback_used": False,
    }


def _run_hwp5txt(
    *,
    bin_path: str,
    hwp_path: Path,
    timeout: int,
) -> _TxtRunResult:
    version = _converter_version(bin_path)
    cmd = [bin_path, str(hwp_path)]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return _TxtRunResult(
            success=False,
            stderr_summary=_truncate_stderr(exc.stderr),
            error_code=ERR_CONVERSION_TIMEOUT,
            error_message=f"HWP hwp5txt timed out after {timeout}s",
            parser_version=version,
        )
    except OSError as exc:
        return _TxtRunResult(
            success=False,
            error_code=ERR_CONVERSION_FAILED,
            error_message=f"HWP hwp5txt failed ({type(exc).__name__})",
            parser_version=version,
        )

    stderr_summary = _truncate_stderr(proc.stderr)
    if proc.returncode != 0:
        err_low = (stderr_summary or "").lower()
        if "password" in err_low or "encrypt" in err_low or "protected" in err_low:
            return _TxtRunResult(
                success=False,
                stderr_summary=stderr_summary,
                error_code=ERR_PASSWORD_PROTECTED,
                error_message="Password protected document",
                parser_version=version,
            )
        return _TxtRunResult(
            success=False,
            stderr_summary=stderr_summary,
            error_code=ERR_CONVERSION_FAILED,
            error_message="HWP hwp5txt conversion failed",
            parser_version=version,
        )

    text, decode_note = _decode_stdout(proc.stdout or b"")
    return _TxtRunResult(
        success=True,
        text=_normalize_text(text),
        stderr_summary=stderr_summary,
        decode_note=decode_note,
        parser_version=version,
    )


def _run_hwp5html(
    *,
    bin_path: str,
    hwp_path: Path,
    timeout: int,
    work_dir: Path,
) -> _HtmlRunResult:
    version = _converter_version(bin_path)
    out_html = work_dir / f"{hwp_path.stem}.html"

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
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                shell=False,
                check=False,
                cwd=str(work_dir) if name == "stdout" else None,
            )
        except subprocess.TimeoutExpired:
            last_err = f"{name}: timeout after {timeout}s"
            continue
        except OSError as exc:
            last_err = f"{name}: {type(exc).__name__}"
            continue

        stderr_summary = _truncate_stderr(proc.stderr)
        if proc.returncode != 0:
            last_err = stderr_summary or f"{name}: exit {proc.returncode}"
            continue

        raw_html = b""
        if name == "stdout":
            raw_html = proc.stdout or b""
        elif out_html.is_file():
            raw_html = out_html.read_bytes()
        else:
            candidates = list(work_dir.glob("*.html")) + list(work_dir.glob("**/*.html"))
            if candidates:
                raw_html = candidates[0].read_bytes()
            else:
                last_err = f"{name}: no html output file"
                continue

        html_text, _note = _decode_file_bytes(raw_html)
        if not html_text.strip():
            last_err = f"{name}: empty html"
            continue

        flatten = flatten_hwp_html(html_text)
        return _HtmlRunResult(
            success=True,
            flatten=flatten,
            stderr_summary=stderr_summary,
            strategy=name,
            parser_version=version,
        )

    return _HtmlRunResult(
        success=False,
        error_summary=last_err or "all hwp5html strategies failed",
        parser_version=version,
    )


def _success_result(
    *,
    text: str,
    converter: str,
    strategy: ExtractionStrategy,
    parser_version: str,
    quality: QualityGrade,
    meta: dict[str, Any],
) -> ParserResult:
    text = _normalize_text(text)
    meta["converter_used"] = converter
    meta["extraction_quality"] = quality
    meta["text_length"] = len(text.encode("utf-8"))
    meta["line_count"] = line_count(text)
    meta["contains_korean"] = bool(_HANGUL_RE.search(text))
    return ParserResult(
        success=True,
        extracted_text=text,
        text_length=len(text),
        parser_name=converter,
        parser_version=parser_version,
        metadata=meta,
    )


def _failure_result(
    *,
    strategy: ExtractionStrategy,
    error_code: str,
    error_message: str,
    meta: dict[str, Any],
    parser_version: str = "unknown",
    extracted_text: str | None = None,
) -> ParserResult:
    return ParserResult(
        success=False,
        extracted_text=extracted_text,
        text_length=len(extracted_text or ""),
        parser_name=PARSER_NAME,
        parser_version=parser_version,
        metadata=meta,
        error_code=error_code,
        error_message=error_message,
    )


def _merge_html_meta(meta: dict[str, Any], flatten: HwpHtmlFlattenResult, html_run: _HtmlRunResult) -> None:
    meta["html_table_count"] = flatten.table_count
    meta["html_table_block_text_size"] = flatten.table_block_text_size
    meta["html_table_block_line_count"] = flatten.table_block_line_count
    meta["html_korean_char_count"] = flatten.korean_char_count
    if html_run.strategy:
        meta["hwp5html_strategy"] = html_run.strategy
    if html_run.stderr_summary:
        meta["stderr_summary"] = html_run.stderr_summary


def _merge_txt_meta(meta: dict[str, Any], text: str, txt_run: _TxtRunResult) -> None:
    meta["txt_table_placeholder_count"] = table_placeholder_count(text)
    meta["txt_korean_char_count"] = korean_char_count(text)
    if txt_run.stderr_summary:
        meta["stderr_summary"] = txt_run.stderr_summary
    if txt_run.decode_note:
        meta["decode_note"] = txt_run.decode_note


class HwpParser(DocumentParser):
    """Extract text from HWP v5 binary via hwp5html and/or hwp5txt subprocesses."""

    PARSER_NAME = PARSER_NAME

    def __init__(self) -> None:
        self._version = "unknown"

    def supports(self, extension: str, mime_type: str | None) -> bool:
        return normalize_extension(extension) == "hwp"

    def parse_bytes(
        self, content: bytes, filename: str, extension: str
    ) -> ParserResult:
        strategy = normalize_hwp_extraction_strategy(settings.hwp_extraction_strategy)
        min_txt = max(0, int(settings.hwp_min_extracted_text_length))
        min_html = max(0, int(settings.hwp_html_min_extracted_text_length))
        min_gain = max(1.0, float(settings.hwp_html_min_gain_ratio))
        timeout = max(1, int(settings.hwp_parser_timeout_seconds))

        if strategy == "hwp5txt_only":
            return self._parse_hwp5txt_only(content, strategy, min_txt, timeout)
        if strategy == "hwp5html_only":
            return self._parse_hwp5html_only(content, strategy, min_html, timeout)
        return self._parse_tiered(content, strategy, min_txt, min_html, min_gain, timeout)

    def _write_temp_hwp(self, content: bytes) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        tmp = tempfile.TemporaryDirectory(prefix="hwp_parse_")
        hwp_path = Path(tmp.name) / f"{uuid.uuid4().hex}.hwp"
        hwp_path.write_bytes(content)
        return tmp, hwp_path

    def _parse_hwp5txt_only(
        self,
        content: bytes,
        strategy: ExtractionStrategy,
        min_len: int,
        timeout: int,
    ) -> ParserResult:
        meta = _base_metadata(strategy)
        bin_path = _resolve_hwp5txt_bin()
        if not bin_path:
            return _failure_result(
                strategy=strategy,
                error_code=ERR_CONVERTER_NOT_AVAILABLE,
                error_message="hwp5txt not available; set HWP5TXT_BIN or install pyhwp",
                meta=meta,
            )

        tmp_holder, hwp_path = self._write_temp_hwp(content)
        with tmp_holder:
            txt_run = _run_hwp5txt(bin_path=bin_path, hwp_path=hwp_path, timeout=timeout)

        if not txt_run.success:
            if txt_run.error_code == ERR_PASSWORD_PROTECTED:
                meta["hwp5txt_error_summary"] = txt_run.error_message
            elif txt_run.stderr_summary:
                meta["hwp5txt_error_summary"] = txt_run.stderr_summary
            return _failure_result(
                strategy=strategy,
                error_code=txt_run.error_code or ERR_CONVERSION_FAILED,
                error_message=txt_run.error_message or "HWP conversion failed",
                meta=meta,
                parser_version=txt_run.parser_version,
            )

        quality = assess_extraction_quality(
            txt_run.text,
            min_meaningful_length=min_len,
        )
        _merge_txt_meta(meta, txt_run.text, txt_run)
        meta["extraction_quality"] = quality

        if not is_txt_path_sufficient(txt_run.text, quality, min_meaningful_length=min_len):
            return _failure_result(
                strategy=strategy,
                error_code=ERR_NO_EXTRACTABLE_TEXT,
                error_message="No extractable text found",
                meta=meta,
                parser_version=txt_run.parser_version,
                extracted_text=txt_run.text or None,
            )

        return _success_result(
            text=txt_run.text,
            converter=CONVERTER_TXT,
            strategy=strategy,
            parser_version=txt_run.parser_version,
            quality=quality,
            meta=meta,
        )

    def _parse_hwp5html_only(
        self,
        content: bytes,
        strategy: ExtractionStrategy,
        min_len: int,
        timeout: int,
    ) -> ParserResult:
        meta = _base_metadata(strategy)
        bin_path = _resolve_hwp5html_bin()
        if not bin_path:
            return _failure_result(
                strategy=strategy,
                error_code=ERR_CONVERTER_NOT_AVAILABLE,
                error_message="hwp5html not available; set HWP5HTML_BIN or install pyhwp",
                meta=meta,
            )

        tmp_holder, hwp_path = self._write_temp_hwp(content)
        with tmp_holder:
            with tempfile.TemporaryDirectory(prefix="hwp5html_") as html_tmp:
                html_run = _run_hwp5html(
                    bin_path=bin_path,
                    hwp_path=hwp_path,
                    timeout=timeout,
                    work_dir=Path(html_tmp),
                )

        if not html_run.success or not html_run.flatten:
            meta["hwp5html_error_summary"] = html_run.error_summary
            return _failure_result(
                strategy=strategy,
                error_code=ERR_CONVERSION_FAILED,
                error_message="HWP hwp5html conversion failed",
                meta=meta,
                parser_version=html_run.parser_version,
            )

        flatten = html_run.flatten
        quality = assess_extraction_quality(
            flatten.text,
            min_meaningful_length=min_len,
            table_count_html=flatten.table_count,
        )
        _merge_html_meta(meta, flatten, html_run)
        meta["extraction_quality"] = quality

        if not is_html_path_sufficient(
            flatten,
            quality,
            min_meaningful_length=min_len,
            min_gain_ratio=1.0,
        ):
            return _failure_result(
                strategy=strategy,
                error_code=ERR_NO_EXTRACTABLE_TEXT,
                error_message="No extractable text found",
                meta=meta,
                parser_version=html_run.parser_version,
                extracted_text=flatten.text or None,
            )

        return _success_result(
            text=flatten.text,
            converter=CONVERTER_HTML,
            strategy=strategy,
            parser_version=html_run.parser_version,
            quality=quality,
            meta=meta,
        )

    def _parse_tiered(
        self,
        content: bytes,
        strategy: ExtractionStrategy,
        min_txt: int,
        min_html: int,
        min_gain: float,
        timeout: int,
    ) -> ParserResult:
        meta = _base_metadata(strategy)
        txt_bin = _resolve_hwp5txt_bin()
        html_bin = _resolve_hwp5html_bin()

        if not txt_bin and not html_bin:
            return _failure_result(
                strategy=strategy,
                error_code=ERR_CONVERTER_NOT_AVAILABLE,
                error_message="Neither hwp5txt nor hwp5html available",
                meta=meta,
            )

        tmp_holder, hwp_path = self._write_temp_hwp(content)
        html_run: _HtmlRunResult | None = None
        txt_run: _TxtRunResult | None = None
        html_attempted = False

        with tmp_holder:
            if html_bin:
                html_attempted = True
                with tempfile.TemporaryDirectory(prefix="hwp5html_") as html_tmp:
                    html_run = _run_hwp5html(
                        bin_path=html_bin,
                        hwp_path=hwp_path,
                        timeout=timeout,
                        work_dir=Path(html_tmp),
                    )
            else:
                meta["hwp5html_error_summary"] = "hwp5html binary not found; skipped"

            if html_run and html_run.success and html_run.flatten:
                flatten = html_run.flatten
                html_quality = assess_extraction_quality(
                    flatten.text,
                    min_meaningful_length=min_html,
                    table_count_html=flatten.table_count,
                )
                _merge_html_meta(meta, flatten, html_run)
                if is_html_path_sufficient(
                    flatten,
                    html_quality,
                    min_meaningful_length=min_html,
                    min_gain_ratio=min_gain,
                ):
                    return _success_result(
                        text=flatten.text,
                        converter=CONVERTER_HTML,
                        strategy=strategy,
                        parser_version=html_run.parser_version,
                        quality=html_quality,
                        meta=meta,
                    )
                meta["hwp5html_insufficient"] = True
            elif html_run and not html_run.success:
                meta["hwp5html_error_summary"] = html_run.error_summary

            if not txt_bin:
                meta["hwp5txt_error_summary"] = "hwp5txt binary not found"
                return _failure_result(
                    strategy=strategy,
                    error_code=ERR_CONVERTER_NOT_AVAILABLE,
                    error_message="hwp5txt not available for tiered fallback",
                    meta=meta,
                    parser_version=html_run.parser_version if html_run else "unknown",
                )

            txt_run = _run_hwp5txt(bin_path=txt_bin, hwp_path=hwp_path, timeout=timeout)

        if not txt_run.success:
            meta["fallback_used"] = html_attempted
            if txt_run.stderr_summary:
                meta["hwp5txt_error_summary"] = txt_run.stderr_summary
            code = txt_run.error_code or ERR_CONVERSION_FAILED
            if code == ERR_PASSWORD_PROTECTED:
                return _failure_result(
                    strategy=strategy,
                    error_code=code,
                    error_message=txt_run.error_message or "Password protected",
                    meta=meta,
                    parser_version=txt_run.parser_version,
                )
            return _failure_result(
                strategy=strategy,
                error_code=ERR_NO_EXTRACTABLE_TEXT
                if html_run and (html_run.success or html_run.error_summary)
                else code,
                error_message="No extractable text found"
                if code != ERR_CONVERSION_TIMEOUT
                else txt_run.error_message or "No extractable text found",
                meta=meta,
                parser_version=txt_run.parser_version,
            )

        txt_quality = assess_extraction_quality(
            txt_run.text,
            min_meaningful_length=min_txt,
        )
        _merge_txt_meta(meta, txt_run.text, txt_run)
        meta["fallback_used"] = html_attempted

        if not is_txt_path_sufficient(txt_run.text, txt_quality, min_meaningful_length=min_txt):
            return _failure_result(
                strategy=strategy,
                error_code=ERR_NO_EXTRACTABLE_TEXT,
                error_message="No extractable text found",
                meta=meta,
                parser_version=txt_run.parser_version,
                extracted_text=txt_run.text or None,
            )

        return _success_result(
            text=txt_run.text,
            converter=CONVERTER_TXT,
            strategy=strategy,
            parser_version=txt_run.parser_version,
            quality=txt_quality,
            meta=meta,
        )


__all__ = ["HwpParser", "normalize_hwp_extraction_strategy"]
