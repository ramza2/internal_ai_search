"""Unit tests for HWP binary parser (no sample .hwp files committed)."""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import MagicMock, patch

from app.parsers.hwp_parser import (
    ERR_CONVERSION_TIMEOUT,
    ERR_CONVERTER_NOT_AVAILABLE,
    ERR_NO_EXTRACTABLE_TEXT,
    HwpParser,
)


class HwpParserSupportsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = HwpParser()

    def test_supports_hwp(self) -> None:
        self.assertTrue(self.parser.supports("hwp", None))
        self.assertTrue(self.parser.supports(".HWP", None))

    def test_does_not_support_hwpx(self) -> None:
        self.assertFalse(self.parser.supports("hwpx", None))


class HwpParserAvailabilityTest(unittest.TestCase):
    @patch("app.parsers.hwp_parser._resolve_hwp5txt_bin", return_value=None)
    def test_converter_not_available(self, _mock_bin: MagicMock) -> None:
        parser = HwpParser()
        result = parser.parse_bytes(b"fake", "x.hwp", "hwp")
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, ERR_CONVERTER_NOT_AVAILABLE)


class HwpParserOutputTest(unittest.TestCase):
    @patch("app.parsers.hwp_parser.settings")
    @patch("app.parsers.hwp_parser._resolve_hwp5txt_bin", return_value="/usr/bin/hwp5txt")
    @patch("app.parsers.hwp_parser.subprocess.run")
    def test_short_text_no_extractable(
        self, mock_run: MagicMock, _mock_bin: MagicMock, mock_settings: MagicMock
    ) -> None:
        mock_settings.hwp_min_extracted_text_length = 50
        mock_settings.hwp_parser_timeout_seconds = 120
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="<표>\n\n".encode("utf-8"), stderr=b""
        )
        parser = HwpParser()
        result = parser.parse_bytes(b"fake", "form.hwp", "hwp")
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, ERR_NO_EXTRACTABLE_TEXT)

    @patch("app.parsers.hwp_parser.settings")
    @patch("app.parsers.hwp_parser._resolve_hwp5txt_bin", return_value="/usr/bin/hwp5txt")
    @patch("app.parsers.hwp_parser.subprocess.run")
    def test_success_with_enough_text(
        self, mock_run: MagicMock, _mock_bin: MagicMock, mock_settings: MagicMock
    ) -> None:
        mock_settings.hwp_min_extracted_text_length = 10
        mock_settings.hwp_parser_timeout_seconds = 120
        body = "연구소기업 사업계획서\n" * 5
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=body.encode("utf-8"), stderr=b"warn\n"
        )
        parser = HwpParser()
        result = parser.parse_bytes(b"fake", "doc.hwp", "hwp")
        self.assertTrue(result.success)
        self.assertIn("연구소기업", result.extracted_text or "")
        self.assertGreaterEqual(result.metadata.get("line_count", 0), 1)

    @patch("app.parsers.hwp_parser.settings")
    @patch("app.parsers.hwp_parser._resolve_hwp5txt_bin", return_value="/usr/bin/hwp5txt")
    @patch("app.parsers.hwp_parser.subprocess.run")
    def test_timeout(
        self, mock_run: MagicMock, _mock_bin: MagicMock, mock_settings: MagicMock
    ) -> None:
        mock_settings.hwp_min_extracted_text_length = 50
        mock_settings.hwp_parser_timeout_seconds = 1
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["hwp5txt"], timeout=1)
        parser = HwpParser()
        result = parser.parse_bytes(b"fake", "big.hwp", "hwp")
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, ERR_CONVERSION_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
