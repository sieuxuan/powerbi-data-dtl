from __future__ import annotations

import unittest

from core.onedrive import _filename_from_headers, _to_download_url


class OneDriveTests(unittest.TestCase):
    def test_to_download_url_adds_download_query(self) -> None:
        self.assertEqual(_to_download_url("https://example.com/file.xlsx"), "https://example.com/file.xlsx?download=1")
        self.assertEqual(
            _to_download_url("https://example.com/file.xlsx?x=1"),
            "https://example.com/file.xlsx?x=1&download=1",
        )
        self.assertEqual(
            _to_download_url("https://docs.google.com/spreadsheets/d/abc123/edit#gid=0"),
            "https://docs.google.com/spreadsheets/d/abc123/export?format=xlsx",
        )
        self.assertEqual(
            _to_download_url("https://drive.google.com/file/d/file123/view?usp=sharing"),
            "https://drive.google.com/uc?export=download&id=file123",
        )

    def test_filename_from_headers(self) -> None:
        self.assertEqual(_filename_from_headers('attachment; filename="report.xlsx"'), "report.xlsx")
        self.assertEqual(_filename_from_headers("attachment; filename*=UTF-8''bao_cao.xlsx"), "bao_cao.xlsx")


if __name__ == "__main__":
    unittest.main()
