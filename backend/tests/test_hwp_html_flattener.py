"""Unit tests for HWP HTML flattening (no sample files)."""

from __future__ import annotations

import unittest

from app.parsers.hwp_html_flattener import flatten_hwp_html


class HwpHtmlFlattenerTest(unittest.TestCase):
    def test_table_marker_and_cell_text(self) -> None:
        html = """
        <html><body>
        <p>공고 제목</p>
        <table><tr><th>관리번호</th><td>001</td></tr>
        <tr><td>품목(문제)명</td><td>에이전틱 AI 과제</td></tr></table>
        </body></html>
        """
        result = flatten_hwp_html(html)
        self.assertIn("--- table 1 ---", result.text)
        self.assertIn("관리번호", result.text)
        self.assertIn("품목(문제)명", result.text)
        self.assertGreaterEqual(result.table_count, 1)
        self.assertGreater(result.table_block_text_size, 0)
        self.assertGreater(result.line_count, 2)

    def test_script_style_ignored(self) -> None:
        html = "<html><script>secret();</script><style>.x{}</style><p>본문</p></html>"
        result = flatten_hwp_html(html)
        self.assertIn("본문", result.text)
        self.assertNotIn("secret", result.text)


if __name__ == "__main__":
    unittest.main()
