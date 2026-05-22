"""HWP extraction quality grades (FULL / PARTIAL / NONE) for tiered parser."""

from __future__ import annotations

import re
from typing import Literal

from app.parsers.hwp_html_flattener import HwpHtmlFlattenResult

QualityGrade = Literal["FULL", "PARTIAL", "NONE"]

_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_DIGIT_RE = re.compile(r"\d")
_TABLE_PLACEHOLDER_RE = re.compile(r"<\s*표\s*>", re.IGNORECASE)
_HIGH_PLACEHOLDER_RATIO = 0.3


def meaningful_text_length(text: str) -> int:
    t = _TABLE_PLACEHOLDER_RE.sub("", text)
    return len(re.sub(r"\s+", "", t))


def table_placeholder_count(text: str) -> int:
    return len(_TABLE_PLACEHOLDER_RE.findall(text))


def korean_char_count(text: str) -> int:
    return len(_HANGUL_RE.findall(text))


def line_count(text: str) -> int:
    return len(text.splitlines()) if text else 0


def assess_extraction_quality(
    text: str,
    *,
    min_meaningful_length: int,
    table_count_html: int = 0,
) -> QualityGrade:
    """Grade one extraction path (hwp5txt or hwp5html flatten)."""
    meaningful = meaningful_text_length(text)
    lines = line_count(text)
    korean = korean_char_count(text)
    placeholders = table_placeholder_count(text)

    if meaningful < min_meaningful_length:
        if table_count_html > 0 and korean >= 20:
            return "PARTIAL"
        return "NONE"

    if lines > 0 and placeholders / max(lines, 1) >= _HIGH_PLACEHOLDER_RATIO:
        if meaningful >= min_meaningful_length and korean >= 30:
            return "PARTIAL"
        return "NONE"

    if meaningful >= min_meaningful_length and (korean >= 30 or _DIGIT_RE.search(text)):
        return "FULL"
    return "PARTIAL"


def is_quality_usable(quality: QualityGrade) -> bool:
    return quality in ("FULL", "PARTIAL")


def is_html_path_sufficient(
    flatten: HwpHtmlFlattenResult,
    quality: QualityGrade,
    *,
    min_meaningful_length: int,
    min_gain_ratio: float,
    txt_meaningful_length: int | None = None,
) -> bool:
    """
    True when tiered extraction should stop after hwp5html (no hwp5txt call).

    Requires usable quality and minimum meaningful length. When txt preview length
    is known and html is only marginally better, require gain ratio.
    """
    if not is_quality_usable(quality):
        return False
    html_len = meaningful_text_length(flatten.text)
    if html_len < min_meaningful_length:
        return False
    if txt_meaningful_length is not None and txt_meaningful_length > 0:
        if html_len < txt_meaningful_length * min_gain_ratio:
            return False
    if quality == "PARTIAL" and flatten.table_block_text_size < min_meaningful_length:
        return html_len >= min_meaningful_length
    return True


def is_txt_path_sufficient(
    text: str,
    quality: QualityGrade,
    *,
    min_meaningful_length: int,
) -> bool:
    if not is_quality_usable(quality):
        return False
    return meaningful_text_length(text) >= min_meaningful_length


__all__ = [
    "QualityGrade",
    "assess_extraction_quality",
    "is_html_path_sufficient",
    "is_quality_usable",
    "is_txt_path_sufficient",
    "korean_char_count",
    "line_count",
    "meaningful_text_length",
    "table_placeholder_count",
]
