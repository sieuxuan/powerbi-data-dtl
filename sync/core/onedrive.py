"""Download file OneDrive public/direct link cho Phase 3 MVP."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse, urlunparse

from .config import DownloadsConfig, SourceConfig
from .schema_compare import normalize_identifier


LOGGER = logging.getLogger(__name__)
FILENAME_PATTERN = re.compile(r"filename\*=UTF-8''([^;]+)|filename=\"?([^\";]+)\"?", re.IGNORECASE)


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
    download_dir = Path(downloads.dir)
    if not download_dir.is_absolute():
        download_dir = base_dir / download_dir
    download_dir.mkdir(parents=True, exist_ok=True)

    with httpx.stream("GET", download_url, follow_redirects=True, timeout=120) as response:
        response.raise_for_status()
        filename = _filename_from_headers(response.headers.get("content-disposition"))
        if not filename:
            filename = _filename_from_url(str(response.url))
        if not filename:
            stem = normalize_identifier(table_name, "download")
            filename = f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        target_path = _unique_path(download_dir / _sanitize_filename(filename))
        with target_path.open("wb") as file_handle:
            for chunk in response.iter_bytes():
                if chunk:
                    file_handle.write(chunk)

    LOGGER.info("Downloaded OneDrive file to %s", target_path)
    return DownloadResult(path=target_path, temporary=not downloads.keep_files)


def _to_download_url(url: str) -> str:
    """Return a best-effort direct download URL for a public OneDrive link."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "download" not in query:
        query["download"] = ["1"]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


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
