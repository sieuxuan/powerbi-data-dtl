from __future__ import annotations

import unittest
from unittest.mock import patch

from core.onedrive import (
    OneDriveError,
    _ensure_download_response_is_file,
    _filename_from_headers,
    _sharepoint_download_url_from_file_url,
    _to_download_url,
    _validate_download_url,
    _validated_download_stream,
    _without_download_query,
)


class FakeResponse:
    def __init__(
        self,
        *,
        is_redirect: bool = False,
        location: str | None = None,
        status_code: int = 200,
        url: str = "https://example.com/file.xlsx",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.is_redirect = is_redirect
        self.status_code = status_code
        self.url = url
        self.headers = headers.copy() if headers else {}
        if location:
            self.headers["location"] = location

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None


class FakeHttpx:
    def __init__(self, responses: list[FakeResponse] | None = None) -> None:
        self.urls: list[str] = []
        self.responses = responses or [FakeResponse(is_redirect=True, location="http://localhost/private.xlsx")]

    def stream(self, _method: str, url: str, *, follow_redirects: bool, timeout: int) -> FakeResponse:
        self.urls.append(url)
        response = self.responses.pop(0)
        response.url = url
        return response


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

    def test_sharepoint_download_url_from_file_url(self) -> None:
        url = (
            "https://tenant.sharepoint.com/sites/Reports/Shared%20Documents/Daily/RMPO%20Data.xlsx"
            "?ga=1&download=1"
        )

        result = _sharepoint_download_url_from_file_url(url)

        self.assertEqual(
            result,
            "https://tenant.sharepoint.com/sites/Reports/_layouts/15/download.aspx"
            "?SourceUrl=%2Fsites%2FReports%2FShared+Documents%2FDaily%2FRMPO+Data.xlsx",
        )

    def test_without_download_query_removes_only_download(self) -> None:
        self.assertEqual(
            _without_download_query("https://tenant.sharepoint.com/sites/Reports/file.xlsx?ga=1&download=1"),
            "https://tenant.sharepoint.com/sites/Reports/file.xlsx?ga=1",
        )

    def test_validated_stream_preserves_sharepoint_redirect_file_url(self) -> None:
        first_url = "https://tenant.sharepoint.com/:x:/s/Reports/token?e=abc&download=1"
        file_url = "https://tenant.sharepoint.com/sites/Reports/Shared%20Documents/Daily/RMPO%20Data.xlsx?ga=1"
        fake_httpx = FakeHttpx(
            [
                FakeResponse(is_redirect=True, location=file_url),
                FakeResponse(status_code=200, url=file_url),
            ]
        )

        with patch("core.onedrive._validate_download_url"):
            with _validated_download_stream(fake_httpx, first_url) as response:
                self.assertEqual(response.status_code, 200)

        self.assertEqual(fake_httpx.urls, [first_url, file_url])

    def test_validated_stream_retries_sharepoint_file_url_without_download_query(self) -> None:
        first_url = "https://tenant.sharepoint.com/sites/Reports/Shared%20Documents/Daily/RMPO%20Data.xlsx?ga=1&download=1"
        retry_url = "https://tenant.sharepoint.com/sites/Reports/Shared%20Documents/Daily/RMPO%20Data.xlsx?ga=1"
        fake_httpx = FakeHttpx(
            [
                FakeResponse(status_code=403, url=first_url),
                FakeResponse(status_code=200, url=retry_url),
            ]
        )

        with patch("core.onedrive._validate_download_url"):
            with _validated_download_stream(fake_httpx, first_url) as response:
                self.assertEqual(response.status_code, 200)

        self.assertEqual(fake_httpx.urls, [first_url, retry_url])

    def test_validated_stream_retries_sharepoint_file_url_with_fallback(self) -> None:
        first_url = "https://tenant.sharepoint.com/sites/Reports/Shared%20Documents/Daily/RMPO%20Data.xlsx?ga=1"
        fake_httpx = FakeHttpx(
            [
                FakeResponse(status_code=403, url=first_url),
                FakeResponse(status_code=200, url="https://tenant.sharepoint.com/sites/Reports/_layouts/15/download.aspx"),
            ]
        )

        with patch("core.onedrive._validate_download_url"):
            with _validated_download_stream(fake_httpx, first_url) as response:
                self.assertEqual(response.status_code, 200)

        self.assertEqual(fake_httpx.urls[0], first_url)
        self.assertIn("/_layouts/15/download.aspx", fake_httpx.urls[1])

    def test_rejects_sharepoint_html_login_response(self) -> None:
        response = FakeResponse(
            headers={"content-type": "text/html; charset=utf-8"},
            url="https://tenant.sharepoint.com/sites/Reports/Shared%20Documents/Daily/RMPO%20Data.xlsx",
        )

        with self.assertRaisesRegex(OneDriveError, "SharePoint did not return"):
            _ensure_download_response_is_file(response)

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
