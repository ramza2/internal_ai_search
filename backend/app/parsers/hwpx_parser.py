"""HWPX (OOXML zip) first-pass text extraction without HWP Automation."""

from __future__ import annotations

import re
import zipfile
from io import BytesIO
from xml.etree import ElementTree

from app.parsers.base import DocumentParser, ParserResult
from app.services.text_extraction_service import normalize_extension

_MAX_XML_BYTES = 2 * 1024 * 1024
_MAX_TOTAL_CHARS = 2_000_000

_SKIP_NAME_RE = re.compile(
    r"(^|/)(mimetype|version\.xml|settings\.xml|manifest\.xml)$|/preview/|/bindata/",
    re.IGNORECASE,
)


def _should_skip_member(name: str) -> bool:
    n = name.replace("\\", "/").strip()
    if not n.lower().endswith(".xml"):
        return True
    return bool(_SKIP_NAME_RE.search(n))


class HwpxParser(DocumentParser):
    PARSER_NAME = "hwpx_parser"
    PARSER_VERSION = "1.0"

    def supports(self, extension: str, mime_type: str | None) -> bool:
        return normalize_extension(extension) == "hwpx"

    def parse_bytes(
        self, content: bytes, filename: str, extension: str
    ) -> ParserResult:
        meta: dict = {"xml_file_count": 0, "parsed_xml_files": 0, "skipped_xml_files": 0}
        collected: list[str] = []
        total_chars = 0

        try:
            zf = zipfile.ZipFile(BytesIO(content))
        except zipfile.BadZipFile:
            return ParserResult(
                success=False,
                extracted_text=None,
                text_length=0,
                parser_name=self.PARSER_NAME,
                parser_version=self.PARSER_VERSION,
                metadata=meta,
                error_code="PARSING_FAILED",
                error_message="Document parsing failed",
            )

        try:
            names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            meta["xml_file_count"] = len(names)
            for name in sorted(names):
                if _should_skip_member(name):
                    meta["skipped_xml_files"] += 1
                    continue
                try:
                    info = zf.getinfo(name)
                    if info.file_size > _MAX_XML_BYTES:
                        meta["skipped_xml_files"] += 1
                        continue
                    raw = zf.read(name)
                except Exception:
                    meta["skipped_xml_files"] += 1
                    continue
                try:
                    root = ElementTree.fromstring(raw)
                except ElementTree.ParseError:
                    meta["skipped_xml_files"] += 1
                    continue

                texts: list[str] = []
                for el in root.iter():
                    t = el.text
                    if t and t.strip():
                        texts.append(t.strip())
                    tail = el.tail
                    if tail and tail.strip():
                        texts.append(tail.strip())
                if texts:
                    chunk = "\n".join(texts)
                    collected.append(f"--- xml: {name} ---\n{chunk}")
                    meta["parsed_xml_files"] += 1
                    total_chars += len(chunk)
                    if total_chars > _MAX_TOTAL_CHARS:
                        break
        finally:
            try:
                zf.close()
            except Exception:
                pass

        text = "\n\n".join(collected).strip()
        return ParserResult(
            success=True,
            extracted_text=text,
            text_length=len(text),
            parser_name=self.PARSER_NAME,
            parser_version=self.PARSER_VERSION,
            metadata=meta,
        )


__all__ = ["HwpxParser"]
