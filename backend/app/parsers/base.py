"""Document parser protocol and shared result type."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParserResult:
    """Outcome of parsing a document from raw bytes."""

    success: bool
    extracted_text: str | None
    text_length: int
    parser_name: str
    parser_version: str
    metadata: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


class DocumentParser(ABC):
    """Pluggable binary → text extraction for office-style documents."""

    @abstractmethod
    def supports(self, extension: str, mime_type: str | None) -> bool:
        """Return True when this parser should handle ``extension`` (lowercase, no dot)."""

    @abstractmethod
    def parse_bytes(
        self, content: bytes, filename: str, extension: str
    ) -> ParserResult:
        """Parse ``content`` for the given logical file name / extension."""


__all__ = ["DocumentParser", "ParserResult"]
