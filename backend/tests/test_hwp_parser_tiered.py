"""Unit tests for tiered HWP parser (subprocess mocked)."""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import MagicMock, patch

from app.parsers.hwp_parser import (
    CONVERTER_HTML,
    CONVERTER_TXT,
    ERR_NO_EXTRACTABLE_TEXT,
    HwpParser,
)


def _settings_mock(
    mock_settings: MagicMock,
    *,
    strategy: str = "tiered",
    min_txt: int = 50,
    min_html: int = 50,
    min_gain: float = 1.5,
) -> None:
    mock_settings.hwp_extraction_strategy = strategy
    mock_settings.hwp5txt_bin = "hwp5txt"
    mock_settings.hwp5html_bin = "hwp5html"
    mock_settings.hwp_parser_timeout_seconds = 120
    mock_settings.hwp_min_extracted_text_length = min_txt
    mock_settings.hwp_html_min_extracted_text_length = min_html
    mock_settings.hwp_html_min_gain_ratio = min_gain


def _is_hwp5html_cmd(cmd: list[str]) -> bool:
    return any("hwp5html" in str(part) for part in cmd) or "--html" in cmd


def _is_hwp5txt_cmd(cmd: list[str]) -> bool:
    return any("hwp5txt" in str(part) for part in cmd) and "--html" not in cmd


class HwpParserTieredTest(unittest.TestCase):
    @patch("app.parsers.hwp_parser.settings")
    @patch("app.parsers.hwp_parser._resolve_hwp5html_bin", return_value="/usr/bin/hwp5html")
    @patch("app.parsers.hwp_parser._resolve_hwp5txt_bin", return_value="/usr/bin/hwp5txt")
    @patch("app.parsers.hwp_parser.subprocess.run")
    def test_tiered_html_sufficient_skips_txt(
        self, mock_run: MagicMock, _t: MagicMock, _h: MagicMock, mock_settings: MagicMock
    ) -> None:
        _settings_mock(mock_settings, min_txt=50, min_html=50)
        html_body = (
            "<html><body><table><tr><td>품목(문제)명</td>"
            f"<td>{'에이전틱 AI 과제 설명 ' * 40}</td></tr></table></body></html>"
        )

        def side_effect(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            if _is_hwp5html_cmd(cmd):
                if "--output" in cmd:
                    return subprocess.CompletedProcess(
                        args=cmd, returncode=1, stdout=b"", stderr=b"skip file output"
                    )
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout=html_body.encode("utf-8"), stderr=b""
                )
            raise AssertionError(f"unexpected cmd: {cmd}")

        mock_run.side_effect = side_effect
        parser = HwpParser()
        result = parser.parse_bytes(b"fake", "form.hwp", "hwp")

        self.assertTrue(result.success)
        self.assertEqual(result.parser_name, CONVERTER_HTML)
        self.assertFalse(result.metadata.get("fallback_used"))
        self.assertEqual(result.metadata.get("converter_used"), CONVERTER_HTML)
        self.assertIn("--- table 1 ---", result.extracted_text or "")
        txt_calls = [c for c in mock_run.call_args_list if _is_hwp5txt_cmd(c[0][0])]
        self.assertEqual(len(txt_calls), 0)

    @patch("app.parsers.hwp_parser.settings")
    @patch("app.parsers.hwp_parser._resolve_hwp5html_bin", return_value="/usr/bin/hwp5html")
    @patch("app.parsers.hwp_parser._resolve_hwp5txt_bin", return_value="/usr/bin/hwp5txt")
    @patch("app.parsers.hwp_parser.subprocess.run")
    def test_tiered_html_fail_falls_back_to_txt(
        self, mock_run: MagicMock, _t: MagicMock, _h: MagicMock, mock_settings: MagicMock
    ) -> None:
        _settings_mock(mock_settings, min_txt=10, min_html=50)
        txt_body = "연구소기업 사업계획서 본문입니다.\n" * 8

        def side_effect(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            if _is_hwp5html_cmd(cmd):
                return subprocess.CompletedProcess(
                    args=cmd, returncode=1, stdout=b"", stderr=b"html failed"
                )
            if _is_hwp5txt_cmd(cmd):
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout=txt_body.encode("utf-8"), stderr=b""
                )
            raise AssertionError(f"unexpected cmd: {cmd}")

        mock_run.side_effect = side_effect
        parser = HwpParser()
        result = parser.parse_bytes(b"fake", "doc.hwp", "hwp")

        self.assertTrue(result.success)
        self.assertEqual(result.parser_name, CONVERTER_TXT)
        self.assertTrue(result.metadata.get("fallback_used"))
        self.assertEqual(result.metadata.get("converter_used"), CONVERTER_TXT)

    @patch("app.parsers.hwp_parser.settings")
    @patch("app.parsers.hwp_parser._resolve_hwp5html_bin", return_value="/usr/bin/hwp5html")
    @patch("app.parsers.hwp_parser._resolve_hwp5txt_bin", return_value="/usr/bin/hwp5txt")
    @patch("app.parsers.hwp_parser.subprocess.run")
    def test_tiered_html_short_falls_back_to_txt(
        self, mock_run: MagicMock, _t: MagicMock, _h: MagicMock, mock_settings: MagicMock
    ) -> None:
        _settings_mock(mock_settings, min_txt=10, min_html=50)
        html_body = "<html><body><p>짧음</p></body></html>"
        txt_body = "충분한 길이의 본문 텍스트입니다. " * 5

        def side_effect(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            if _is_hwp5html_cmd(cmd):
                if "--output" in cmd:
                    return subprocess.CompletedProcess(
                        args=cmd, returncode=1, stdout=b"", stderr=b"skip"
                    )
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout=html_body.encode("utf-8"), stderr=b""
                )
            if _is_hwp5txt_cmd(cmd):
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout=txt_body.encode("utf-8"), stderr=b""
                )
            raise AssertionError(f"unexpected cmd: {cmd}")

        mock_run.side_effect = side_effect
        parser = HwpParser()
        result = parser.parse_bytes(b"fake", "doc.hwp", "hwp")

        self.assertTrue(result.success)
        self.assertEqual(result.metadata.get("converter_used"), CONVERTER_TXT)
        self.assertTrue(result.metadata.get("fallback_used"))

    @patch("app.parsers.hwp_parser.settings")
    @patch("app.parsers.hwp_parser._resolve_hwp5html_bin", return_value="/usr/bin/hwp5html")
    @patch("app.parsers.hwp_parser._resolve_hwp5txt_bin", return_value="/usr/bin/hwp5txt")
    @patch("app.parsers.hwp_parser.subprocess.run")
    def test_tiered_both_insufficient_no_extractable(
        self, mock_run: MagicMock, _t: MagicMock, _h: MagicMock, mock_settings: MagicMock
    ) -> None:
        _settings_mock(mock_settings)
        html_body = "<html><body><p>x</p></body></html>"

        def side_effect(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            if _is_hwp5html_cmd(cmd):
                if "--output" in cmd:
                    return subprocess.CompletedProcess(
                        args=cmd, returncode=1, stdout=b"", stderr=b"skip"
                    )
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout=html_body.encode("utf-8"), stderr=b""
                )
            if _is_hwp5txt_cmd(cmd):
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="<표>\n".encode("utf-8"), stderr=b""
                )
            raise AssertionError(f"unexpected cmd: {cmd}")

        mock_run.side_effect = side_effect
        parser = HwpParser()
        result = parser.parse_bytes(b"fake", "form.hwp", "hwp")

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, ERR_NO_EXTRACTABLE_TEXT)
        self.assertTrue(result.metadata.get("fallback_used"))

    @patch("app.parsers.hwp_parser.settings")
    @patch("app.parsers.hwp_parser._resolve_hwp5html_bin", return_value=None)
    @patch("app.parsers.hwp_parser._resolve_hwp5txt_bin", return_value="/usr/bin/hwp5txt")
    @patch("app.parsers.hwp_parser.subprocess.run")
    def test_hwp5txt_only_strategy(
        self, mock_run: MagicMock, _t: MagicMock, _h: MagicMock, mock_settings: MagicMock
    ) -> None:
        _settings_mock(mock_settings, strategy="hwp5txt_only", min_txt=10)
        body = "본문 텍스트가 충분히 있습니다. " * 4
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=body.encode("utf-8"), stderr=b""
        )
        parser = HwpParser()
        result = parser.parse_bytes(b"fake", "doc.hwp", "hwp")
        self.assertTrue(result.success)
        self.assertEqual(result.metadata.get("converter_used"), CONVERTER_TXT)
        self.assertEqual(result.metadata.get("extraction_strategy"), "hwp5txt_only")
        html_calls = [c for c in mock_run.call_args_list if _is_hwp5html_cmd(c[0][0])]
        self.assertEqual(len(html_calls), 0)


if __name__ == "__main__":
    unittest.main()
