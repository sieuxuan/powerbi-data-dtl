"""Download file OneDrive public/direct link cho Phase 3 MVP."""

from __future__ import annotations

import logging
import ipaddress
import re
import socket
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlparse, urlunparse

from .config import DownloadsConfig, SourceConfig
from .schema_compare import normalize_identifier


LOGGER = logging.getLogger(__name__)
FILENAME_PATTERN = re.compile(r"filename\*=UTF-8''([^;]+)|filename=\"?([^\";]+)\"?", re.IGNORECASE)
MAX_DOWNLOAD_BYTES = 250 * 1024 * 1024
MAX_REDIRECTS = 10
OFFICE_FILE_EXTENSIONS = {".csv", ".xls", ".xlsx", ".xlsm", ".xlsb"}
SHAREPOINT_AUTH_ERROR = (
    "SharePoint did not return a downloadable file. The link may require sign-in, "
    "the sharing permission may have changed, or the file is no longer public. "
    "Open the link in a browser and create a new downloadable sharing link, or use a local OneDrive path."
)
DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*;q=0.8"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}


class OneDriveError(RuntimeError):
    """Raised when a OneDrive file cannot be downloaded."""


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    temporary: bool


def download_onedrive_file(
    source: SourceConfig,
    downloads: DownloadsConfig,
    base_dir: Path,
    table_name: str,
) -> DownloadResult:
    """Download a public OneDrive/direct URL into the configured download directory."""
    url = source.download_url or source.share_url
    if not url:
        raise OneDriveError("OneDrive source requires download_url or share_url.")

    try:
        import httpx
    except ImportError as exc:
        raise OneDriveError("httpx is required. Install dependencies with: pip install -r requirements.txt") from exc

    download_url = _to_download_url(url)
    _validate_download_url(download_url)
    download_dir = Path(downloads.dir)
    if not download_dir.is_absolute():
        download_dir = base_dir / download_dir
    download_dir.mkdir(parents=True, exist_ok=True)

    with _validated_download_stream(httpx, download_url) as response:
        _raise_for_download_status(response)
        _ensure_download_response_is_file(response)
        length = response.headers.get("content-length")
        if length:
            try:
                if int(length) > MAX_DOWNLOAD_BYTES:
                    raise OneDriveError("Downloaded file is too large. Limit is 250 MB.")
            except ValueError:
                LOGGER.debug("Ignoring invalid content-length header: %s", length)
        filename = _filename_from_headers(response.headers.get("content-disposition"))
        if not filename:
            filename = _filename_from_url(str(response.url))
        if not filename:
            stem = normalize_identifier(table_name, "download")
            filename = f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        target_path = _unique_path(download_dir / _sanitize_filename(filename))
        total_bytes = 0
        try:
            with target_path.open("wb") as file_handle:
                for chunk in response.iter_bytes():
                    if chunk:
                        total_bytes += len(chunk)
                        if total_bytes > MAX_DOWNLOAD_BYTES:
                            raise OneDriveError("Downloaded file is too large. Limit is 250 MB.")
                        file_handle.write(chunk)
        except Exception:
            target_path.unlink(missing_ok=True)
            raise

    LOGGER.info("Downloaded OneDrive file to %s", target_path)
    return DownloadResult(path=target_path, temporary=not downloads.keep_files)


@contextmanager
def _validated_download_stream(httpx: Any, url: str) -> Iterator[Any]:
    """Open a streaming response while validating every redirect target."""
    client_factory = getattr(httpx, "Client", None)
    if client_factory is not None:
        with client_factory(headers=DOWNLOAD_HEADERS, follow_redirects=False, timeout=120) as client:
            with _validated_download_stream_from_client(client, url) as response:
                yield response
                return
    with _validated_download_stream_from_client(httpx, url) as response:
        yield response


@contextmanager
def _validated_download_stream_from_client(client: Any, url: str) -> Iterator[Any]:
    """Open a streaming response using one client so SharePoint redirect cookies are preserved."""
    current_url = url
    for _redirect_count in range(MAX_REDIRECTS + 1):
        _validate_download_url(current_url)
        with client.stream("GET", current_url, follow_redirects=False, timeout=120) as response:
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise OneDriveError("Download redirect is missing a Location header.")
                current_url = urljoin(current_url, location)
                continue
            if getattr(response, "status_code", 200) in {401, 403} and _is_sharepoint_file_url(current_url):
                retry_url = _without_download_query(current_url)
                if retry_url != current_url:
                    LOGGER.info("SharePoint direct file URL was blocked; retrying without download query.")
                    current_url = retry_url
                    continue
                fallback_url = _sharepoint_download_url_from_file_url(current_url)
                if fallback_url and fallback_url != current_url:
                    LOGGER.info("SharePoint direct file URL was blocked; retrying download.aspx fallback.")
                    current_url = fallback_url
                    continue
            yield response
            return
    raise OneDriveError("Download link redirected too many times.")


def _to_download_url(url: str) -> str:
    """Return a best-effort direct download URL for a public online spreadsheet link."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.endswith("docs.google.com") and "/spreadsheets/d/" in parsed.path:
        parts = [part for part in parsed.path.split("/") if part]
        sheet_id = parts[parts.index("d") + 1] if "d" in parts and parts.index("d") + 1 < len(parts) else ""
        if sheet_id:
            return urlunparse(
                parsed._replace(
                    path=f"/spreadsheets/d/{sheet_id}/export",
                    query=urlencode({"format": "xlsx"}),
                    fragment="",
                )
            )
    if host.endswith("drive.google.com") and "/file/d/" in parsed.path:
        parts = [part for part in parsed.path.split("/") if part]
        file_id = parts[parts.index("d") + 1] if "d" in parts and parts.index("d") + 1 < len(parts) else ""
        if file_id:
            return urlunparse(
                parsed._replace(
                    path="/uc",
                    query=urlencode({"export": "download", "id": file_id}),
                    fragment="",
                )
            )
    query = parse_qs(parsed.query)
    if "download" not in query:
        query["download"] = ["1"]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def _raise_for_download_status(response: Any) -> None:
    """Raise a user-focused error for authentication-like download failures."""
    status_code = getattr(response, "status_code", 200)
    response_url = str(getattr(response, "url", ""))
    if status_code in {401, 403} and _source_kind(response_url) == "sharepoint":
        raise OneDriveError(SHAREPOINT_AUTH_ERROR)
    response.raise_for_status()


def _ensure_download_response_is_file(response: Any) -> None:
    """Reject HTML/login responses that are not real spreadsheet downloads."""
    response_url = str(getattr(response, "url", ""))
    parsed = urlparse(response_url)
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    path = parsed.path.lower()
    if content_type == "text/html":
        if _source_kind(response_url) == "sharepoint":
            raise OneDriveError(SHAREPOINT_AUTH_ERROR)
        raise OneDriveError("Download URL returned HTML instead of a file.")
    if "login.microsoftonline.com" in parsed.netloc.lower() or "/_forms/" in path:
        raise OneDriveError(SHAREPOINT_AUTH_ERROR)


def _with_download_query(url: str) -> str:
    """Add download=1 to a URL while preserving existing query parameters."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "download" not in query:
        query["download"] = ["1"]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True), fragment=""))


def _without_download_query(url: str) -> str:
    """Remove SharePoint's download query when it blocks direct file access."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "download" not in query:
        return url
    query.pop("download", None)
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True), fragment=""))


def _is_sharepoint_file_url(url: str) -> bool:
    """Return True when a URL points directly at a SharePoint spreadsheet file."""
    parsed = urlparse(url)
    if "sharepoint.com" not in parsed.netloc.lower():
        return False
    suffix = Path(unquote(parsed.path)).suffix.lower()
    return suffix in OFFICE_FILE_EXTENSIONS


def _sharepoint_download_url_from_file_url(url: str) -> str | None:
    """Build SharePoint's download.aspx URL for a direct site file URL."""
    parsed = urlparse(url)
    if not _is_sharepoint_file_url(url):
        return None
    source_path = unquote(parsed.path)
    site_path = _sharepoint_site_path(source_path)
    if not site_path:
        return None
    query = urlencode({"SourceUrl": source_path})
    return urlunparse(parsed._replace(path=f"{site_path}/_layouts/15/download.aspx", query=query, fragment=""))


def _sharepoint_site_path(path: str) -> str | None:
    """Extract /sites/name or /teams/name from a SharePoint file path."""
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) < 2:
        return None
    if parts[0].lower() not in {"sites", "teams"}:
        return None
    return f"/{parts[0]}/{parts[1]}"


def _source_kind(url: str) -> str:
    """Return a coarse provider label for an online file URL."""
    host = urlparse(url).netloc.lower()
    if "docs.google.com" in host or "drive.google.com" in host:
        return "google"
    if "sharepoint.com" in host or "1drv.ms" in host or "onedrive.live.com" in host:
        return "sharepoint"
    return "direct"


def _validate_download_url(url: str) -> None:
    """Reject unsupported or local network URLs before downloading."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise OneDriveError("Only http/https links are allowed.")
    host = parsed.hostname
    if not host:
        raise OneDriveError("Download link is missing a hostname.")
    if host.lower() in {"localhost", "localhost.localdomain"}:
        raise OneDriveError("Localhost links are not allowed.")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise OneDriveError(f"Could not resolve download host: {host}") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_multicast or ip.is_unspecified:
            raise OneDriveError("Private or local network links are not allowed.")


def _filename_from_headers(content_disposition: str | None) -> str | None:
    """Extract filename from a Content-Disposition header."""
    if not content_disposition:
        return None
    match = FILENAME_PATTERN.search(content_disposition)
    if not match:
        return None
    value = match.group(1) or match.group(2)
    return unquote(value.strip()) if value else None


def _filename_from_url(url: str) -> str | None:
    """Extract a plausible filename from a URL path."""
    name = Path(unquote(urlparse(url).path)).name
    if "." not in name:
        return None
    return name


def _sanitize_filename(filename: str) -> str:
    """Return a filesystem-safe filename."""
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", filename).strip(" .")
    return sanitized or f"download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"


def _unique_path(path: Path) -> Path:
    """Avoid overwriting an existing downloaded file."""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 10_000):
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise OneDriveError(f"Could not allocate a unique download path for {path}")
