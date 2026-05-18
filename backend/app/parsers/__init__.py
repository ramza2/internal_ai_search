"""Document parser adapters (PDF, Office Open XML, HWPX, …)."""

from __future__ import annotations

from app.parsers.base import DocumentParser, ParserResult

__all__ = [
    "DocumentParser",
    "ParserResult",
    "get_parser_for_extension",
    "supported_document_extensions",
]


def __getattr__(name: str):
    if name == "get_parser_for_extension":
        from app.parsers.registry import get_parser_for_extension as fn

        return fn
    if name == "supported_document_extensions":
        from app.parsers.registry import supported_document_extensions as fn

        return fn
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
