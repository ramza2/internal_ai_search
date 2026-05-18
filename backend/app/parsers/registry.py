"""Parser registry for office-style document extensions."""

from __future__ import annotations

from app.parsers.base import DocumentParser
from app.parsers.docx_parser import DocxParser
from app.parsers.hwp_parser import HwpParser
from app.parsers.hwpx_parser import HwpxParser
from app.parsers.pdf_parser import PdfParser
from app.parsers.plain_text_parser import PlainTextParser
from app.parsers.pptx_parser import PptxParser
from app.parsers.unsupported_parser import UnsupportedParser
from app.parsers.xlsx_parser import XlsxParser
from app.services.text_extraction_service import normalize_extension

_DOCUMENT_EXTENSIONS: frozenset[str] = frozenset(
    {"pdf", "docx", "xlsx", "pptx", "hwpx", "hwp"}
)

_ORDERED: tuple[DocumentParser, ...] = (
    PdfParser(),
    DocxParser(),
    XlsxParser(),
    PptxParser(),
    HwpParser(),
    HwpxParser(),
    PlainTextParser(),
)


def supported_document_extensions() -> frozenset[str]:
    """Extensions handled by the document processing API (subset of parsers)."""
    return _DOCUMENT_EXTENSIONS


def get_parser_for_extension(extension: str) -> DocumentParser:
    """Resolve the first parser that supports ``extension`` (case-insensitive)."""
    ext = normalize_extension(extension)
    for parser in _ORDERED:
        if parser.supports(ext, None):
            return parser
    return UnsupportedParser()


__all__ = [
    "get_parser_for_extension",
    "supported_document_extensions",
]
