"""Document parser adapters (PDF, Office Open XML, HWPX, …)."""

from app.parsers.base import DocumentParser, ParserResult
from app.parsers.registry import get_parser_for_extension, supported_document_extensions

__all__ = [
    "DocumentParser",
    "ParserResult",
    "get_parser_for_extension",
    "supported_document_extensions",
]
