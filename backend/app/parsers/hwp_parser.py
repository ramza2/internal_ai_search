"""HWP binary (.hwp) text extraction via hwp5txt CLI (no Automation/COM)."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from app.core.config import settings
from app.parsers.base import DocumentParser, ParserResult
from app.services.text_extraction_service import normalize_extension

logger = logging.getLogger(__name__)

_STDERR_MAX = 1000
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")

ERR_CONVERTER_NOT_AVAILABLE = "HWP_CONVERTER_NOT_AVAILABLE"
ERR_CONVERSION_FAILED = "HWP_CONVERSION_FAILED"
ERR_CONVERSION_TIMEOUT = "HWP_CONVERSION_TIMEOUT"
ERR_NO_EXTRACTABLE_TEXT = "NO_EXTRACTABLE_TEXT"
ERR_PASSWORD_PROTECTED = "PASSWORD_PROTECTED"

CONVERTER_NAME = "hwp5txt"


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


def _resolve_hwp5txt_bin() -> str | None:
    configured = (settings.hwp5txt_bin or "hwp5txt").strip()
    if not configured:
        return None
    found = shutil.which(configured)
    if found:
        return found
    path = Path(configured)
    if path.is_file():
        return str(path.resolve())
    return None


def _decode_stdout(raw: bytes) -> tuple[str, str | None]:
    if not raw:
        return "", None
    for enc in ("utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(enc), None
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "stdout decoded with utf-8 errors=replace"


def _normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _stripped_length(text: str) -> int:
    return len("".join(text.split()))


def _line_count(text: str) -> int:
    if not text:
        return 0
    return len(text.splitlines())


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


class HwpParser(DocumentParser):
    """Extract plain text from HWP v5 binary via external ``hwp5txt`` subprocess."""

    PARSER_NAME = "hwp_parser"

    def __init__(self) -> None:
        self._version = "unknown"

    def supports(self, extension: str, mime_type: str | None) -> bool:
        return normalize_extension(extension) == "hwp"

    def parse_bytes(
        self, content: bytes, filename: str, extension: str
    ) -> ParserResult:
        meta: dict = {
            "source_format": "hwp",
            "converter": CONVERTER_NAME,
        }
        bin_path = _resolve_hwp5txt_bin()
        if not bin_path:
            return ParserResult(
                success=False,
                extracted_text=None,
                text_length=0,
                parser_name=CONVERTER_NAME,
                parser_version=self._version,
                metadata=meta,
                error_code=ERR_CONVERTER_NOT_AVAILABLE,
                error_message="hwp5txt converter not available on PATH",
            )

        parser_version = _converter_version(bin_path)
        min_len = max(0, int(settings.hwp_min_extracted_text_length))
        timeout = max(1, int(settings.hwp_parser_timeout_seconds))

        try:
            with tempfile.TemporaryDirectory(prefix="hwp_parse_") as tmp:
                hwp_path = Path(tmp) / f"{uuid.uuid4().hex}.hwp"
                hwp_path.write_bytes(content)
                cmd = [bin_path, str(hwp_path)]
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=timeout,
                    shell=False,
                    check=False,
                )
        except subprocess.TimeoutExpired as exc:
            stderr_summary = _truncate_stderr(exc.stderr)
            if stderr_summary:
                meta["stderr_summary"] = stderr_summary
            return ParserResult(
                success=False,
                extracted_text=None,
                text_length=0,
                parser_name=CONVERTER_NAME,
                parser_version=parser_version,
                metadata=meta,
                error_code=ERR_CONVERSION_TIMEOUT,
                error_message=f"HWP conversion timed out after {timeout}s",
            )
        except OSError as exc:
            return ParserResult(
                success=False,
                extracted_text=None,
                text_length=0,
                parser_name=CONVERTER_NAME,
                parser_version=parser_version,
                metadata=meta,
                error_code=ERR_CONVERSION_FAILED,
                error_message=f"HWP conversion failed: {type(exc).__name__}",
            )

        stderr_summary = _truncate_stderr(proc.stderr)
        if stderr_summary:
            meta["stderr_summary"] = stderr_summary

        if proc.returncode != 0:
            err_low = (stderr_summary or "").lower()
            if "password" in err_low or "encrypt" in err_low or "protected" in err_low:
                return ParserResult(
                    success=False,
                    extracted_text=None,
                    text_length=0,
                    parser_name=CONVERTER_NAME,
                    parser_version=parser_version,
                    metadata=meta,
                    error_code=ERR_PASSWORD_PROTECTED,
                    error_message="Password protected document",
                )
            return ParserResult(
                success=False,
                extracted_text=None,
                text_length=0,
                parser_name=CONVERTER_NAME,
                parser_version=parser_version,
                metadata=meta,
                error_code=ERR_CONVERSION_FAILED,
                error_message="HWP conversion failed",
            )

        text, decode_note = _decode_stdout(proc.stdout or b"")
        text = _normalize_text(text)
        if decode_note:
            meta["decode_note"] = decode_note

        meta["line_count"] = _line_count(text)
        meta["text_length"] = len(text.encode("utf-8"))
        meta["contains_korean"] = bool(_HANGUL_RE.search(text))

        if _stripped_length(text) < min_len:
            return ParserResult(
                success=False,
                extracted_text=text or None,
                text_length=len(text),
                parser_name=CONVERTER_NAME,
                parser_version=parser_version,
                metadata=meta,
                error_code=ERR_NO_EXTRACTABLE_TEXT,
                error_message="No extractable text found",
            )

        return ParserResult(
            success=True,
            extracted_text=text,
            text_length=len(text),
            parser_name=CONVERTER_NAME,
            parser_version=parser_version,
            metadata=meta,
        )


__all__ = ["HwpParser"]
