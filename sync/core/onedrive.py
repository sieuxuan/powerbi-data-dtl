"""Download file OneDrive public/direct link cho Phase 3 MVP."""

from __future__ import annotations

import logging
import ipaddress
import re
import socket
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse, urlunparse

from .config import DownloadsConfig, SourceConfig
from .schema_compare import normalize_identifier


LOGGER = logging.getLogger(__name__)
FILENAME_PATTERN = re.compile(r"filename\*=UTF-8''([^;]+)|filename=\"?([^\";]+)\"?", re.IGNORECASE)
MAX_DOWNLOAD_BYTES = 250 * 1024 * 1024


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

    with httpx.stream("GET", download_url, follow_redirects=True, timeout=120) as response:
        response.raise_for_status()
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
