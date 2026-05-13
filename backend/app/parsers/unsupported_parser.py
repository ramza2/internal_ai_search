"""Fallback parser for extensions with no dedicated implementation."""

from __future__ import annotations

from app.parsers.base import DocumentParser, ParserResult
from app.services.text_extraction_service import normalize_extension


class UnsupportedParser(DocumentParser):
    PARSER_NAME = "unsupported_parser"
    PARSER_VERSION = "0.1"

    def supports(self, extension: str, mime_type: str | None) -> bool:
        return False

    def parse_bytes(
        self, content: bytes, filename: str, extension: str
    ) -> ParserResult:
        ext = normalize_extension(extension)
        return ParserResult(
            success=False,
            extracted_text=None,
            text_length=0,
            parser_name=self.PARSER_NAME,
            parser_version=self.PARSER_VERSION,
            metadata={"extension": ext},
            error_code="UNSUPPORTED_EXTENSION",
            error_message="Unsupported document extension",
        )


__all__ = ["UnsupportedParser"]
