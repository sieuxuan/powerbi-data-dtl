from __future__ import annotations

import unittest
from unittest.mock import patch

from core.onedrive import (
    OneDriveError,
    _filename_from_headers,
    _to_download_url,
    _validate_download_url,
    _validated_download_stream,
)


class FakeResponse:
    def __init__(self, *, is_redirect: bool, location: str | None = None) -> None:
        self.is_redirect = is_redirect
        self.headers = {"location": location} if location else {}

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        return None


class FakeHttpx:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def stream(self, _method: str, url: str, *, follow_redirects: bool, timeout: int) -> FakeResponse:
        self.urls.append(url)
        return FakeResponse(is_redirect=True, location="http://localhost/private.xlsx")


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

    def test_download_url_rejects_localhost(self) -> None:
        with self.assertRaises(OneDriveError):
            _validate_download_url("http://localhost/report.xlsx")

    def test_validated_stream_revalidates_redirect_target(self) -> None:
        fake_httpx = FakeHttpx()

        def validate(url: str) -> None:
            if url.startswith("http://localhost"):
                raise OneDriveError("Private or local network links are not allowed.")

        with patch("core.onedrive._validate_download_url", side_effect=validate):
            with self.assertRaises(OneDriveError):
                with _validated_download_stream(fake_httpx, "https://example.com/start.xlsx"):
                    pass

        self.assertEqual(fake_httpx.urls, ["https://example.com/start.xlsx"])


if __name__ == "__main__":
    unittest.main()
