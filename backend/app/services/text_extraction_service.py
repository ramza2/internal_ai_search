"""Plain-text extraction primitives for Step 12.

Owns three orthogonal concerns so the orchestrator stays small:

1. ``SUPPORTED_EXTENSIONS`` — the explicit allow-list of extensions this
   milestone is allowed to read as plain text. PDF/DOCX/HWP/XLSX/images
   are deliberately excluded and rejected before any download.
2. ``looks_binary`` — a cheap heuristic over the raw byte body that flags
   probably-binary payloads (NULL-byte density ≥ 1 %).
3. ``decode_bytes`` — a deterministic fallback chain
   ``utf-8-sig → utf-8 → cp949 → euc-kr → latin-1``. ``latin-1`` accepts
   every byte and so always succeeds; the chain is built specifically to
   keep Korean text intact when an upstream tool has saved a file in a
   legacy MS code page.

This module never touches the database, the network, or the configured
data source — it is safe to unit-test with raw bytes.
"""

from __future__ import annotations


PARSER_NAME = "plain_text_extractor"
PARSER_VERSION = "0.1"

# Allow-list. The orchestrator rejects everything outside this set with
# ``analysis_error_code='UNSUPPORTED_EXTENSION'`` before any download.
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {
        # Document-like text
        "txt", "md", "markdown", "csv", "log",
        # Source code
        "py",
        "java", "kt",
        "js", "ts", "tsx", "jsx",
        "c", "cpp", "h", "hpp",
        "cs", "go", "rs", "php", "rb", "swift", "sql",
        "html", "css", "scss", "vue",
        # Config
        "json", "xml", "yaml", "yml",
        "ini", "conf", "properties", "env", "toml",
    }
)

# Anything denser than this is treated as a binary payload disguised as
# something with a text-y extension (e.g. a renamed PNG).
_BINARY_NULL_BYTE_RATIO_THRESHOLD = 0.01

_DECODE_FALLBACKS: tuple[str, ...] = (
    "utf-8-sig",
    "utf-8",
    "cp949",
    "euc-kr",
    "latin-1",
)


def normalize_extension(value: str | None) -> str:
    """Lowercase, strip surrounding whitespace, drop a leading dot."""
    if value is None:
        return ""
    s = str(value).strip().lower()
    if not s:
        return ""
    if s.startswith("."):
        s = s[1:].strip()
    return s


def is_supported_extension(value: str | None) -> bool:
    """Return ``True`` when this file extension is in the allow-list."""
    return normalize_extension(value) in SUPPORTED_EXTENSIONS


def looks_binary(body: bytes) -> bool:
    """Heuristic: ≥1 % NULL bytes ⇒ treat as binary.

    Empty bodies are *not* flagged as binary; downstream code handles them
    as a normal "empty file" path so we still upsert a zero-length text.
    """
    if not body:
        return False
    null_count = body.count(b"\x00")
    return (null_count / len(body)) >= _BINARY_NULL_BYTE_RATIO_THRESHOLD


def decode_bytes(body: bytes) -> tuple[str | None, str | None]:
    """Return ``(text, encoding_used)`` or ``(None, summary)`` on failure.

    Walks ``_DECODE_FALLBACKS`` and accepts the first encoding that
    decodes without raising. ``latin-1`` never raises, so this function
    succeeds for every non-empty byte string in practice — the ``None``
    branch is kept as a defensive fall-through.
    """
    if not body:
        return "", "utf-8"
    last_error: str = ""
    for enc in _DECODE_FALLBACKS:
        try:
            return body.decode(enc), enc
        except (UnicodeDecodeError, LookupError) as exc:
            last_error = f"{enc}: {type(exc).__name__}"
            continue
    return None, last_error or "All decoding attempts failed"


def parse_include_extensions(raw: str | None) -> frozenset[str] | None:
    """Parse the ``include_extensions`` query (comma-separated).

    Returns ``None`` when nothing was requested (no filter applied);
    otherwise a normalized lowercase ``frozenset`` of extension tokens.
    """
    if raw is None:
        return None
    items = [
        normalize_extension(part)
        for part in str(raw).split(",")
        if part is not None
    ]
    tokens = {item for item in items if item}
    if not tokens:
        return None
    return frozenset(tokens)
