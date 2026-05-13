"""PDF text extraction via pypdf (no OCR)."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.parsers._versions import package_version
from app.parsers.base import DocumentParser, ParserResult
from app.services.text_extraction_service import normalize_extension


class PdfParser(DocumentParser):
    PARSER_NAME = "pdf_parser"

    def __init__(self) -> None:
        self._version = package_version("pypdf")

    def supports(self, extension: str, mime_type: str | None) -> bool:
        return normalize_extension(extension) == "pdf"

    def parse_bytes(
        self, content: bytes, filename: str, extension: str
    ) -> ParserResult:
        meta: dict = {}
        try:
            reader = PdfReader(BytesIO(content), strict=False)
        except PdfReadError as exc:
            msg = str(exc).lower()
            if "password" in msg or "encrypted" in msg:
                return ParserResult(
                    success=False,
                    extracted_text=None,
                    text_length=0,
                    parser_name=self.PARSER_NAME,
                    parser_version=self._version,
                    metadata=meta,
                    error_code="PASSWORD_PROTECTED",
                    error_message="Password protected document",
                )
            return ParserResult(
                success=False,
                extracted_text=None,
                text_length=0,
                parser_name=self.PARSER_NAME,
                parser_version=self._version,
                metadata=meta,
                error_code="PARSING_FAILED",
                error_message="Document parsing failed",
            )
        except Exception:
            return ParserResult(
                success=False,
                extracted_text=None,
                text_length=0,
                parser_name=self.PARSER_NAME,
                parser_version=self._version,
                metadata=meta,
                error_code="PARSING_FAILED",
                error_message="Document parsing failed",
            )

        meta["page_count"] = len(reader.pages)
        try:
            meta["encrypted"] = bool(reader.is_encrypted)
        except Exception:
            meta["encrypted"] = False

        if reader.is_encrypted:
            try:
                rc = reader.decrypt("")
            except Exception:
                rc = 0
            if rc == 0:
                return ParserResult(
                    success=False,
                    extracted_text=None,
                    text_length=0,
                    parser_name=self.PARSER_NAME,
                    parser_version=self._version,
                    metadata=meta,
                    error_code="PASSWORD_PROTECTED",
                    error_message="Password protected document",
                )

        title_val = None
        try:
            info = reader.metadata
            if info and info.title:
                title_val = str(info.title).strip() or None
        except Exception:
            title_val = None
        if title_val:
            meta["title"] = title_val

        parts: list[str] = []
        for i, page in enumerate(reader.pages, start=1):
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            t = t.strip()
            if t:
                parts.append(f"--- page {i} ---\n{t}")

        text = "\n\n".join(parts).strip()
        return ParserResult(
            success=True,
            extracted_text=text,
            text_length=len(text),
            parser_name=self.PARSER_NAME,
            parser_version=self._version,
            metadata=meta,
        )


__all__ = ["PdfParser"]
