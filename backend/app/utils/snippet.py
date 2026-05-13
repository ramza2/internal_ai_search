"""Snippet builder for search results.

Pure-Python helper used by the search service to turn a raw
``chunk_text`` into a ≤ 300-character preview that:

- normalizes whitespace (newlines + tabs collapsed to single spaces),
- prefers a window centered on a case-insensitive query match when the
  query string actually appears in the chunk,
- falls back to the leading 300 characters when the query is not a
  literal substring (the embedding similarity still rank-orders these
  hits — the snippet is just a UI affordance),
- adds leading / trailing ``…`` ellipses only when content was
  actually trimmed on that side, so a short chunk renders without
  decoration.

The full ``chunk_text`` is *never* returned: only the trimmed snippet.
That contract matches the project's logging policy too — the snippet
is the only thing safe to surface back to the caller or to logs.
"""

from __future__ import annotations

import re


SNIPPET_MAX_LEN = 300
_WHITESPACE_RUN = re.compile(r"\s+")
_ELLIPSIS = "\u2026"  # U+2026 HORIZONTAL ELLIPSIS — one character, not "..."


def _normalize_whitespace(text: str) -> str:
    """Collapse every whitespace run (newlines, tabs, NBSP, …) to a single space.

    ``str.replace('\\n', ' ')`` alone would leave ``\\r`` and tabs
    behind; the regex form handles every Unicode whitespace category
    in one pass. Leading / trailing whitespace is stripped because a
    snippet preview that opens with ``" foo"`` looks like a bug.
    """
    return _WHITESPACE_RUN.sub(" ", text).strip()


def _find_first_match(haystack: str, needle: str) -> int:
    """Case-insensitive first-occurrence index, or ``-1`` when absent.

    The match is always against the *normalized* haystack so callers do
    not have to keep two indices in sync. Returning ``-1`` keeps the
    contract identical to :py:meth:`str.find` so callers can branch
    cleanly on the result.
    """
    if not needle:
        return -1
    try:
        return haystack.lower().find(needle.lower())
    except Exception:
        return -1


def build_snippet(
    chunk_text: str | None,
    query: str | None,
    *,
    max_len: int = SNIPPET_MAX_LEN,
) -> str:
    """Return a ≤ ``max_len`` preview of ``chunk_text`` keyed off ``query``.

    Behaviour, by priority:

    1. ``chunk_text`` is ``None`` or empty after normalization → ``""``.
    2. ``query`` literally appears in the normalized text → centre a
       window on the first match, balanced left / right; ellipses are
       only inserted on the trimmed side(s).
    3. No literal match → return the normalized leading ``max_len``
       characters, suffix-ellipsis when the text was longer than that.

    ``max_len`` is treated as the *total* visible length **including**
    any ellipses, so the resulting string is guaranteed to fit a UI
    column declared as ``max_len`` cells.
    """
    if not chunk_text or max_len <= 0:
        return ""

    normalized = _normalize_whitespace(str(chunk_text))
    if not normalized:
        return ""

    if len(normalized) <= max_len:
        return normalized

    trimmed_query = (query or "").strip()
    match_index = _find_first_match(normalized, trimmed_query) if trimmed_query else -1

    if match_index < 0:
        return _truncate_suffix(normalized, max_len)

    # Center a window on the match. We reserve up to two ellipsis chars
    # so the visible budget stays under ``max_len`` regardless of which
    # sides get trimmed.
    needle_len = len(trimmed_query)
    # Effective body length without the worst-case ellipsis budget.
    body_budget = max_len - 2  # reserve room for ‹……›
    if body_budget <= needle_len:
        # Pathological case: the query alone is longer than the
        # available budget. Fall back to head-truncation so we still
        # return *something* useful for the operator.
        return _truncate_suffix(normalized, max_len)

    half = max(0, (body_budget - needle_len) // 2)
    start = match_index - half
    end = match_index + needle_len + half

    # Snap the window back into the string. We extend the *other* end
    # when one side hits a boundary so we use the whole budget.
    if start < 0:
        end += -start
        start = 0
    if end > len(normalized):
        start -= (end - len(normalized))
        end = len(normalized)
        if start < 0:
            start = 0

    has_prefix_ellipsis = start > 0
    has_suffix_ellipsis = end < len(normalized)

    # Re-tighten the window when both ellipses fit so the final
    # rendered string is still ≤ max_len.
    while True:
        rendered_len = (end - start)
        rendered_len += 1 if has_prefix_ellipsis else 0
        rendered_len += 1 if has_suffix_ellipsis else 0
        if rendered_len <= max_len:
            break
        # Trim one char from whichever side currently buys us the
        # least context (prefer trimming the tail).
        if has_suffix_ellipsis and end > match_index + needle_len:
            end -= 1
        elif has_prefix_ellipsis and start < match_index:
            start += 1
        else:
            break

    body = normalized[start:end]
    prefix = _ELLIPSIS if has_prefix_ellipsis else ""
    suffix = _ELLIPSIS if has_suffix_ellipsis else ""
    return f"{prefix}{body}{suffix}"


def _truncate_suffix(normalized: str, max_len: int) -> str:
    """Head + suffix-ellipsis truncation used when the query did not match."""
    if len(normalized) <= max_len:
        return normalized
    # Reserve 1 char for the ellipsis when we actually trim.
    cut = max_len - 1
    if cut <= 0:
        return _ELLIPSIS
    return normalized[:cut] + _ELLIPSIS


def build_snippet_with_tokens(
    chunk_text: str | None,
    query: str | None,
    tokens: list[str] | None,
    *,
    max_len: int = SNIPPET_MAX_LEN,
) -> str:
    """Snippet builder that also considers a list of keyword tokens.

    Step-17 keyword / hybrid mode needs better snippet placement when
    the full ``query`` phrase isn't in the chunk but one of its
    whitespace-split tokens is. Algorithm:

    1. Try the full ``query`` phrase first (delegates to
       :func:`build_snippet`). If it matches, we're done.
    2. Otherwise scan ``tokens`` (longest first so a multi-word
       partial wins over a stop-word) and reuse the same window logic
       around the earliest occurrence.
    3. Fall back to the head-truncation path when nothing matches.

    The function never returns more than ``max_len`` characters and
    never exposes the full ``chunk_text``.
    """
    if not chunk_text or max_len <= 0:
        return ""

    # Fast path: the whole-phrase logic handles short texts and full
    # matches already (centered window + ellipses).
    base = build_snippet(chunk_text, query, max_len=max_len)
    if base and (not query or _find_first_match(_normalize_whitespace(chunk_text), (query or "").strip()) >= 0):
        return base

    # No full-phrase match — try tokens.
    normalized = _normalize_whitespace(str(chunk_text))
    if not normalized or len(normalized) <= max_len:
        return normalized

    # Pick the earliest match across all tokens (longest first so
    # multi-character tokens take precedence over single-char ones).
    earliest_token: str | None = None
    earliest_idx = -1
    if tokens:
        for tok in sorted(
            (t for t in tokens if t and len(t.strip()) > 0),
            key=lambda t: -len(t),
        ):
            idx = _find_first_match(normalized, tok)
            if idx < 0:
                continue
            if earliest_idx < 0 or idx < earliest_idx:
                earliest_token = tok
                earliest_idx = idx

    if earliest_token is None:
        return _truncate_suffix(normalized, max_len)

    # Re-use the centered-window path by recursing on the matching
    # token as the synthetic "query".
    return build_snippet(chunk_text, earliest_token, max_len=max_len)


__all__ = [
    "SNIPPET_MAX_LEN",
    "build_snippet",
    "build_snippet_with_tokens",
]
