"""Extension → file type classification (used by the file statistics API).

This module owns the canonical mapping; both Python-side classification
(``classify_extension``) and the SQL ``CASE`` expression
(``FILE_TYPE_CASE_SQL`` over ``lower(extension)``) derive from the same
constants so the report and the database aggregation never diverge.
"""

from __future__ import annotations

from enum import StrEnum


class FileType(StrEnum):
    DOCUMENT = "DOCUMENT"
    SOURCE_CODE = "SOURCE_CODE"
    CONFIG = "CONFIG"
    LOG = "LOG"
    ARCHIVE = "ARCHIVE"
    IMAGE = "IMAGE"
    AUDIO_VIDEO = "AUDIO_VIDEO"
    BINARY = "BINARY"
    UNKNOWN = "UNKNOWN"


# Lowercase, no leading dot. Keep entries unique per category.
_DOCUMENT_EXTS: frozenset[str] = frozenset({
    "txt", "md", "markdown",
    "pdf",
    "doc", "docx",
    "hwp", "hwpx",
    "ppt", "pptx",
    "xls", "xlsx",
    "csv",
})

_SOURCE_CODE_EXTS: frozenset[str] = frozenset({
    "py",
    "java", "kt",
    "js", "ts", "tsx", "jsx",
    "c", "cpp", "h", "hpp",
    "cs",
    "go",
    "rs",
    "php",
    "rb",
    "swift",
    "sql",
    "html", "css", "scss",
    "vue",
})

_CONFIG_EXTS: frozenset[str] = frozenset({
    "json", "xml",
    "yaml", "yml",
    "ini", "conf", "properties",
    "env",
    "toml",
})

_LOG_EXTS: frozenset[str] = frozenset({"log"})

_ARCHIVE_EXTS: frozenset[str] = frozenset({
    "zip", "7z", "rar", "tar", "gz", "tgz",
})

_IMAGE_EXTS: frozenset[str] = frozenset({
    "png", "jpg", "jpeg", "gif", "bmp", "webp", "svg", "psd", "ai",
})

_AUDIO_VIDEO_EXTS: frozenset[str] = frozenset({
    "mp3", "wav",
    "mp4", "avi", "mov", "mkv", "webm",
})

_BINARY_EXTS: frozenset[str] = frozenset({
    "exe", "dll", "so", "dylib",
    "class", "jar", "war", "ear",
    "bin", "o", "obj",
})


_FILE_TYPE_BUCKETS: tuple[tuple[FileType, frozenset[str]], ...] = (
    (FileType.DOCUMENT, _DOCUMENT_EXTS),
    (FileType.SOURCE_CODE, _SOURCE_CODE_EXTS),
    (FileType.CONFIG, _CONFIG_EXTS),
    (FileType.LOG, _LOG_EXTS),
    (FileType.ARCHIVE, _ARCHIVE_EXTS),
    (FileType.IMAGE, _IMAGE_EXTS),
    (FileType.AUDIO_VIDEO, _AUDIO_VIDEO_EXTS),
    (FileType.BINARY, _BINARY_EXTS),
)


def _normalize_extension(value: str | None) -> str:
    """Return a lowercased, dot-stripped extension token (or ``""`` for none)."""
    if value is None:
        return ""
    s = str(value).strip().lower()
    if not s:
        return ""
    if s.startswith("."):
        s = s[1:].strip()
    return s


def classify_extension(value: str | None) -> str:
    """Map an extension (any case, with/without dot, ``None``) → ``FileType`` label.

    Returns ``"UNKNOWN"`` for empty/None values or anything outside the
    declared sets.
    """
    norm = _normalize_extension(value)
    if not norm:
        return FileType.UNKNOWN.value
    for label, members in _FILE_TYPE_BUCKETS:
        if norm in members:
            return label.value
    return FileType.UNKNOWN.value


def _sql_str_literal(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _build_file_type_case_sql(column_expr: str) -> str:
    """Build a deterministic ``CASE`` mapping lowercase ext → file type label.

    All inputs originate from internal constants — there is no user-supplied
    SQL here. ``column_expr`` should be the column reference for the file's
    extension, e.g. ``"f.extension"``; the helper wraps it with ``lower(...)``
    and treats ``NULL``/empty values as ``UNKNOWN`` via the final ``ELSE``.
    """
    lines: list[str] = ["CASE"]
    norm_col = f"lower(nullif(trim({column_expr}), ''))"
    for label, members in _FILE_TYPE_BUCKETS:
        if not members:
            continue
        literals = ", ".join(_sql_str_literal(m) for m in sorted(members))
        lines.append(f"  WHEN {norm_col} IN ({literals}) THEN '{label.value}'")
    lines.append("  ELSE 'UNKNOWN'")
    lines.append("END")
    return "\n".join(lines)


FILE_TYPE_CASE_SQL: str = _build_file_type_case_sql("extension")


def humanize_bytes(n: int | None) -> str:
    """Render a byte count with binary units (KB = 1024). ``None``/≤0 → ``"0 B"``."""
    if n is None:
        return "0 B"
    try:
        value = int(n)
    except (TypeError, ValueError):
        return "0 B"
    if value <= 0:
        return "0 B"

    units = ("B", "KB", "MB", "GB", "TB", "PB", "EB")
    size = float(value)
    idx = 0
    while size >= 1024.0 and idx < len(units) - 1:
        size /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(size)} B"
    return f"{size:.2f} {units[idx]}"
