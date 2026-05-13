"""Plain-text parser for registry completeness (not used by document batch API)."""

from __future__ import annotations

from app.parsers.base import DocumentParser, ParserResult
from app.services.text_extraction_service import (
    SUPPORTED_EXTENSIONS,
    decode_bytes,
    normalize_extension,
)


class PlainTextParser(DocumentParser):
    PARSER_NAME = "plain_text_parser"
    PARSER_VERSION = "0.1"

    def supports(self, extension: str, mime_type: str | None) -> bool:
        return normalize_extension(extension) in SUPPORTED_EXTENSIONS

    def parse_bytes(
        self, content: bytes, filename: str, extension: str
    ) -> ParserResult:
        text, enc = decode_bytes(content)
        if text is None:
            return ParserResult(
                success=False,
                extracted_text=None,
                text_length=0,
                parser_name=self.PARSER_NAME,
                parser_version=self.PARSER_VERSION,
                metadata={},
                error_code="PARSING_FAILED",
                error_message="Failed to decode file body as text",
            )
        return ParserResult(
            success=True,
            extracted_text=text,
            text_length=len(text),
            parser_name=self.PARSER_NAME,
            parser_version=self.PARSER_VERSION,
            metadata={"encoding_hint": enc},
        )


__all__ = ["PlainTextParser"]
