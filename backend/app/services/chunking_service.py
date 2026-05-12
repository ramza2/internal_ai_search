"""Character-based chunking primitives for Step 13.

Pure: no database, no network, no settings. Operates on a plain string
and returns structured chunk records that the orchestrator can persist
into ``document_chunks``.

The splitter favors paragraph boundaries when one is reachable inside
the look-back window (``\\n`` near the nominal chunk end); otherwise it
falls back to a clean character cut so we always make forward progress.
Line numbers (``start_line`` / ``end_line``) are derived from the
**normalized** text — the same string we save into ``chunk_text`` — so
downstream "open file at line N" actions line up with what the chunk
actually contains.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# Defensive ceilings: the route layer also constrains these via FastAPI
# ``Query``, but the service hardens against direct in-process callers.
CHUNK_SIZE_MIN = 200
CHUNK_SIZE_MAX = 10_000

# Look-back distance from the nominal chunk end where we'll try to land
# on a ``\\n`` paragraph boundary. Capped at 25 % of ``chunk_size`` so
# the boundary search can never push the chunk below
# ``chunk_size * 0.75`` characters.
_BOUNDARY_LOOKBACK_RATIO = 0.25


class ChunkingParameterError(ValueError):
    """Raised when chunk_size / chunk_overlap / min_chunk_size are invalid."""


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    start_offset: int
    end_offset: int
    start_line: int  # 1-based
    end_line: int  # 1-based, inclusive
    token_count: int


def validate_chunk_params(
    *, chunk_size: int, chunk_overlap: int, min_chunk_size: int
) -> None:
    """Raise ``ChunkingParameterError`` with a human-readable reason.

    The route layer turns this into a ``400`` response with
    ``error=<reason>``; the service layer also calls it so direct
    in-process callers get the same guarantees.
    """
    if chunk_size < CHUNK_SIZE_MIN:
        raise ChunkingParameterError(
            f"chunk_size must be >= {CHUNK_SIZE_MIN}"
        )
    if chunk_size > CHUNK_SIZE_MAX:
        raise ChunkingParameterError(
            f"chunk_size must be <= {CHUNK_SIZE_MAX}"
        )
    if chunk_overlap < 0:
        raise ChunkingParameterError("chunk_overlap must be >= 0")
    if chunk_overlap >= chunk_size:
        raise ChunkingParameterError(
            "chunk_overlap must be smaller than chunk_size"
        )
    if min_chunk_size < 0:
        raise ChunkingParameterError("min_chunk_size must be >= 0")


# Collapse a run of 3+ blank lines down to a single blank line so very
# generously spaced markdown / code doesn't waste chunk budget on empty
# space. Matched against the *normalized* text (``\\r\\n``/`\\r`` already
# folded to ``\\n``).
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    """Canonicalize line endings + trim run-away blank-line padding.

    Output uses ``\\n`` exclusively; trailing whitespace on a line is
    preserved (matters for indentation-sensitive source code).
    """
    if not text:
        return ""
    s = text.replace("\r\n", "\n").replace("\r", "\n")
    s = _EXCESS_BLANK_LINES.sub("\n\n", s)
    return s


def _count_tokens(chunk_text: str) -> int:
    """Cheap whitespace-split token count (placeholder until tokenizer)."""
    if not chunk_text:
        return 0
    return len(chunk_text.split())


def _build_line_starts(text: str) -> list[int]:
    """Return the 0-based offsets where each line begins.

    ``lines[0] == 0`` always (line 1 starts at offset 0). For every
    ``\\n`` at offset ``i``, the next line starts at ``i + 1``.
    """
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def _offset_to_line(line_starts: list[int], offset: int) -> int:
    """Binary-search the 1-based line number containing ``offset``."""
    if offset <= 0:
        return 1
    lo, hi = 0, len(line_starts) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if line_starts[mid] <= offset:
            lo = mid + 1
        else:
            hi = mid - 1
    return max(1, hi + 1)


def _choose_cut(text: str, *, nominal_end: int, min_cut: int) -> int:
    """Find the best cut point in ``[min_cut, nominal_end]``.

    Prefers the rightmost ``\\n`` (paragraph boundary) in the window; if
    none is present, falls back to ``nominal_end`` for a clean
    character cut. Always returns a value within the window so forward
    progress is guaranteed.
    """
    if nominal_end >= len(text):
        return len(text)
    window_lo = max(min_cut, 0)
    if window_lo >= nominal_end:
        return nominal_end
    boundary = text.rfind("\n", window_lo, nominal_end)
    if boundary == -1:
        return nominal_end
    return boundary + 1  # include the newline in the previous chunk


def estimate_chunk_count(
    text_length: int, *, chunk_size: int, chunk_overlap: int
) -> int:
    """Closed-form chunk count for ``text_length`` characters.

    Used by ``dry_run`` to avoid materializing chunks. Equivalent to
    ``ceil((text_length - chunk_overlap) / step)`` with ``step =
    chunk_size - chunk_overlap``, clamped to ``[0, ∞)``.
    """
    if text_length <= 0:
        return 0
    step = chunk_size - chunk_overlap
    if step <= 0:
        return 1
    if text_length <= chunk_size:
        return 1
    return 1 + ((text_length - chunk_size) + step - 1) // step


def split_text_into_chunks(
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
    min_chunk_size: int,
) -> list[Chunk]:
    """Slice ``text`` into ``Chunk`` records with offsets + line numbers.

    The caller is responsible for normalizing ``text`` first (call
    :func:`normalize_text`); the splitter assumes ``\\n`` line endings
    and uses the same string for line-number calculations as it writes
    into ``chunk_text``.

    A tail shorter than ``min_chunk_size`` is **merged into the previous
    chunk** rather than emitted as its own micro-chunk. When the whole
    text is shorter than ``min_chunk_size`` the function returns ``[]``
    — the orchestrator surfaces that as ``SKIPPED / TEXT_TOO_SHORT``.
    """
    validate_chunk_params(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        min_chunk_size=min_chunk_size,
    )
    if not text:
        return []
    if len(text) < min_chunk_size:
        return []

    line_starts = _build_line_starts(text)
    step = chunk_size - chunk_overlap

    chunks: list[tuple[int, int]] = []  # (start_offset, end_offset)
    start = 0
    text_len = len(text)
    boundary_window = max(1, int(chunk_size * _BOUNDARY_LOOKBACK_RATIO))

    while start < text_len:
        nominal_end = min(start + chunk_size, text_len)
        if nominal_end >= text_len:
            cut = text_len
        else:
            min_cut = max(start + 1, nominal_end - boundary_window)
            cut = _choose_cut(text, nominal_end=nominal_end, min_cut=min_cut)
        chunks.append((start, cut))
        if cut >= text_len:
            break
        next_start = cut - chunk_overlap
        if next_start <= start:
            next_start = start + step  # forward-progress guarantee
        start = next_start

    # Merge a too-short tail into the previous chunk so we don't emit
    # micro-chunks that hurt retrieval ranking later.
    if len(chunks) >= 2:
        tail_start, tail_end = chunks[-1]
        if (tail_end - tail_start) < min_chunk_size:
            prev_start, _prev_end = chunks[-2]
            chunks[-2] = (prev_start, tail_end)
            chunks.pop()

    out: list[Chunk] = []
    for i, (s, e) in enumerate(chunks):
        chunk_text = text[s:e]
        start_line = _offset_to_line(line_starts, s)
        # ``e`` is exclusive; line of last character is ``e - 1``
        end_line = _offset_to_line(line_starts, max(s, e - 1))
        out.append(
            Chunk(
                index=i,
                text=chunk_text,
                start_offset=s,
                end_offset=e,
                start_line=start_line,
                end_line=end_line,
                token_count=_count_tokens(chunk_text),
            )
        )
    return out


__all__ = [
    "CHUNK_SIZE_MIN",
    "CHUNK_SIZE_MAX",
    "Chunk",
    "ChunkingParameterError",
    "estimate_chunk_count",
    "normalize_text",
    "split_text_into_chunks",
    "validate_chunk_params",
]
