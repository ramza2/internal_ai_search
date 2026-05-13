"""Query-term highlight positions for file preview (Step 18).

Splits ``query`` on whitespace, drops tokens shorter than 2 characters,
then scans each line case-insensitively for literal substring matches.
Returns at most ``max_highlights`` hits. Per line, matches are
**non-overlapping** (greedy left-to-right by start offset).

Offsets are **0-based within the line text** (the raw line without a
``"123: "`` prefix).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN_SPLIT = re.compile(r"\s+")
_MIN_TOKEN_LEN = 2
_DEFAULT_MAX_HIGHLIGHTS = 100


@dataclass(frozen=True)
class HighlightSpan:
    term: str
    line: int
    start_offset: int
    end_offset: int

    def as_dict(self) -> dict[str, str | int]:
        return {
            "term": self.term,
            "line": self.line,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
        }


def normalize_highlight_tokens(query: str | None) -> list[str]:
    """Lowercased unique tokens, length ≥ ``_MIN_TOKEN_LEN``."""
    if not query or not (query := query.strip()):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in _TOKEN_SPLIT.split(query):
        tok = raw.strip().lower()
        if len(tok) < _MIN_TOKEN_LEN:
            continue
        if tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out


def _line_hits(lower_line: str, tokens: list[str]) -> list[tuple[int, int, str]]:
    """All (start, end, term) inclusive-exclusive offsets in ``lower_line``."""
    hits: list[tuple[int, int, str]] = []
    for term in tokens:
        start = 0
        while start < len(lower_line):
            idx = lower_line.find(term, start)
            if idx < 0:
                break
            hits.append((idx, idx + len(term), term))
            start = idx + 1
    hits.sort(key=lambda t: (t[0], t[1]))
    return hits


def _greedy_pick_non_overlap(
    hits: list[tuple[int, int, str]], max_take: int
) -> list[tuple[int, int, str]]:
    picked: list[tuple[int, int, str]] = []
    last_end = -1
    for s, e, term in hits:
        if s >= last_end:
            picked.append((s, e, term))
            last_end = e
            if len(picked) >= max_take:
                break
    return picked


def find_highlights_in_lines(
    lines: list[tuple[int, str]],
    query: str | None,
    *,
    max_highlights: int = _DEFAULT_MAX_HIGHLIGHTS,
) -> list[dict[str, str | int]]:
    """Collect highlight dicts for ``(line_number, line_text)`` rows."""
    tokens = normalize_highlight_tokens(query)
    if not tokens or not lines:
        return []

    out: list[HighlightSpan] = []
    for line_no, text in lines:
        if len(out) >= max_highlights:
            break
        lower = text.lower()
        raw_hits = _line_hits(lower, tokens)
        budget = max_highlights - len(out)
        for s, e, term in _greedy_pick_non_overlap(raw_hits, budget):
            surface = text[s:e]
            out.append(
                HighlightSpan(
                    term=surface if surface else term,
                    line=line_no,
                    start_offset=s,
                    end_offset=e,
                )
            )
            if len(out) >= max_highlights:
                break
    return [s.as_dict() for s in out]


__all__ = [
    "HighlightSpan",
    "find_highlights_in_lines",
    "normalize_highlight_tokens",
]
