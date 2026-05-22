"""Flatten hwp5html output to line-oriented plain text for search/RAG (stdlib only)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

_TABLE_BLOCK_RE = re.compile(r"^---\s*table\s+\d+\s*---\s*$", re.IGNORECASE)
_TABLE_PLACEHOLDER_RE = re.compile(r"<\s*표\s*>", re.IGNORECASE)
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")


@dataclass(frozen=True)
class HwpHtmlFlattenResult:
    text: str
    table_count: int
    table_block_count: int
    table_block_line_count: int
    table_block_text_size: int
    table_text_estimate: int
    korean_char_count: int
    line_count: int


class _HtmlFlattenParser(HTMLParser):
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
        if t == "tr":
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


def _meaningful_len(text: str) -> int:
    t = _TABLE_PLACEHOLDER_RE.sub("", text)
    return len(re.sub(r"\s+", "", t))


def _analyze_table_blocks(flat: str) -> tuple[int, int, int, int]:
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
    return (
        len(blocks),
        sum(len(b) for b in blocks),
        len(total_text.encode("utf-8")),
        _meaningful_len(total_text),
    )


def _naive_strip_html(html: str) -> tuple[str, int]:
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.I | re.S)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    flat = "\n".join(ln for ln in lines if ln) + ("\n" if lines else "")
    return flat, 0


def flatten_hwp_html(html: str) -> HwpHtmlFlattenResult:
    """Convert hwp5html HTML to searchable plain text with ``--- table N ---`` markers."""
    parser = _HtmlFlattenParser()
    try:
        parser.feed(html)
        parser.close()
        flat = parser.get_text()
        table_count = parser.table_count
    except Exception:
        flat, table_count = _naive_strip_html(html)

    block_count, block_lines, block_size, table_estimate = _analyze_table_blocks(flat)
    line_count = len(flat.splitlines()) if flat else 0
    return HwpHtmlFlattenResult(
        text=flat,
        table_count=table_count,
        table_block_count=block_count,
        table_block_line_count=block_lines,
        table_block_text_size=block_size,
        table_text_estimate=table_estimate,
        korean_char_count=len(_HANGUL_RE.findall(flat)),
        line_count=line_count,
    )


__all__ = ["HwpHtmlFlattenResult", "flatten_hwp_html"]
