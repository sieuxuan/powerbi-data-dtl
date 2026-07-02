"""Check and download portable updates from GitHub Releases."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import UpdateConfig


LOGGER = logging.getLogger(__name__)
DEFAULT_UPDATE_REPO = "sieuxuan/powerbi-data-dtl"
DEFAULT_ASSET_PATTERN = "PowerBIDataDTL-portable.zip"


class UpdateError(RuntimeError):
    """Raised when update metadata or assets cannot be fetched."""


@dataclass(frozen=True)
class UpdateInfo:
    """Result of a GitHub release update check."""

    configured: bool
    update_available: bool
    current_version: str
    latest_version: str | None = None
    release_url: str | None = None
    asset_name: str | None = None
    asset_url: str | None = None
    downloaded_path: str | None = None
    extracted_path: str | None = None
    apply_script: str | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly payload."""
        return {
            "configured": self.configured,
            "update_available": self.update_available,
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "release_url": self.release_url,
            "asset_name": self.asset_name,
            "asset_url": self.asset_url,
            "downloaded_path": self.downloaded_path,
            "extracted_path": self.extracted_path,
            "apply_script": self.apply_script,
            "message": self.message,
        }


def check_for_update(config: UpdateConfig, base_dir: Path | None = None) -> UpdateInfo:
    """Check GitHub Releases and return latest matching asset metadata."""
    repo = _repo(config)
    current_version = _current_version(config, base_dir)
    if not config.enabled or not repo:
        return UpdateInfo(
            configured=False,
            update_available=False,
            current_version=current_version,
            message="Chưa bật kiểm tra cập nhật hoặc chưa cấu hình GitHub repo.",
        )

    release = _fetch_latest_release(config, repo)
    latest_version = _normalize_version(str(release.get("tag_name") or release.get("name") or ""))
    if not latest_version:
        raise UpdateError("Latest GitHub release has no tag_name.")
    asset = _find_asset(release.get("assets", []), _asset_pattern(config))
    update_available = _version_tuple(latest_version) > _version_tuple(current_version)
    downloaded_path = None
    if update_available and asset and base_dir is not None:
        downloaded_path = _existing_download_path(config, base_dir, str(asset.get("name") or ""), latest_version)
    return UpdateInfo(
        configured=True,
        update_available=update_available,
        current_version=current_version,
        latest_version=latest_version,
        release_url=release.get("html_url"),
        asset_name=asset.get("name") if asset else None,
        asset_url=asset.get("browser_download_url") if asset else None,
        downloaded_path=str(downloaded_path) if downloaded_path else None,
        message="Có bản mới. Hãy tải gói cập nhật trước khi cài." if update_available else "Đang dùng bản mới nhất.",
    )


def download_update(config: UpdateConfig, base_dir: Path) -> UpdateInfo:
    """Download the latest matching GitHub release asset."""
    info = check_for_update(config, base_dir)
    if not info.update_available:
        return info
    if not info.asset_url or not info.asset_name:
        raise UpdateError("No matching release asset was found.")

    try:
        import httpx
    except ImportError as exc:
        raise UpdateError("httpx is required. Install dependencies with: pip install -r requirements.txt") from exc

    download_dir = _download_dir(config, base_dir)
    download_dir.mkdir(parents=True, exist_ok=True)
    target_path = _download_target_path(download_dir, info.asset_name, info.latest_version)
    if target_path.exists() and target_path.stat().st_size > 0:
        LOGGER.info("Update asset is already downloaded at %s", target_path)
        return UpdateInfo(
            configured=info.configured,
            update_available=info.update_available,
            current_version=info.current_version,
            latest_version=info.latest_version,
            release_url=info.release_url,
            asset_name=info.asset_name,
            asset_url=info.asset_url,
            downloaded_path=str(target_path),
            message=f"Gói cập nhật đã được tải sẵn tại {target_path}.",
        )

    partial_path = target_path.with_suffix(f"{target_path.suffix}.part")
    try:
        with httpx.stream("GET", info.asset_url, follow_redirects=True, timeout=300) as response:
            response.raise_for_status()
            with partial_path.open("wb") as file_handle:
                for chunk in response.iter_bytes():
                    if chunk:
                        file_handle.write(chunk)
        partial_path.replace(target_path)
    except Exception as exc:
        partial_path.unlink(missing_ok=True)
        raise UpdateError(f"Could not download update asset: {exc}") from exc

    LOGGER.info("Downloaded update asset to %s", target_path)
    return UpdateInfo(
        configured=info.configured,
        update_available=info.update_available,
        current_version=info.current_version,
        latest_version=info.latest_version,
        release_url=info.release_url,
        asset_name=info.asset_name,
        asset_url=info.asset_url,
        downloaded_path=str(target_path),
        message=f"Đã tải gói cập nhật vào {target_path}.",
    )


def check_and_download_if_enabled(config: UpdateConfig, base_dir: Path) -> UpdateInfo:
    """Check for updates and optionally download the latest asset."""
    info = check_for_update(config, base_dir)
    if info.update_available and config.auto_download:
        return download_update(config, base_dir)
    return info


def apply_update(config: UpdateConfig, base_dir: Path, *, restart: bool = False) -> UpdateInfo:
    """Download, stage, and optionally launch a self-update script."""
    if not _is_portable_root(base_dir.parent):
        raise UpdateError("Auto apply is only supported in the portable app folder.")

    info = download_update(config, base_dir)
    if not info.update_available:
        return info
    if not info.downloaded_path:
        raise UpdateError("Update asset was not downloaded.")

    zip_path = Path(info.downloaded_path)
    stage_dir = _extract_update(zip_path, base_dir, info.latest_version or "update")
    source_root = _find_portable_root(stage_dir)
    script_path = _write_apply_script(
        target_root=base_dir.parent,
        source_root=source_root,
        current_pid=os.getpid(),
        tray_pid=_env_int("POWERBI_DTL_TRAY_PID"),
        launcher_path=_launcher_path_from_env(),
        version=info.latest_version or "update",
    )
    message = f"Đã chuẩn bị bản cập nhật tại {source_root}. Chạy {script_path} để cài."
    if restart:
        _launch_apply_script(script_path)
        _exit_process_soon()
        message = "Đang cài cập nhật. Ứng dụng sẽ đóng runtime cũ và tự mở lại."

    return UpdateInfo(
        configured=info.configured,
        update_available=info.update_available,
        current_version=info.current_version,
        latest_version=info.latest_version,
        release_url=info.release_url,
        asset_name=info.asset_name,
        asset_url=info.asset_url,
        downloaded_path=info.downloaded_path,
        extracted_path=str(source_root),
        apply_script=str(script_path),
        message=message,
    )


def _fetch_latest_release(config: UpdateConfig, repo: str) -> dict[str, Any]:
    """Fetch latest release metadata from GitHub."""
    try:
        import httpx
    except ImportError as exc:
        raise UpdateError("httpx is required. Install dependencies with: pip install -r requirements.txt") from exc

    url = f"https://api.github.com/repos/{repo}/releases"
    try:
        response = httpx.get(url, headers={"Accept": "application/vnd.github+json"}, timeout=30)
        response.raise_for_status()
        releases = response.json()
    except Exception as exc:
        raise UpdateError(f"Could not fetch GitHub releases for {repo}: {exc}") from exc
    if not isinstance(releases, list):
        raise UpdateError("Unexpected GitHub releases response.")
    for release in releases:
        if release.get("draft"):
            continue
        if release.get("prerelease") and not config.allow_prerelease:
            continue
        return release
    raise UpdateError("No suitable GitHub release was found.")


def _find_asset(assets: Any, pattern: str) -> dict[str, Any] | None:
    """Find the first release asset matching the configured pattern."""
    if not isinstance(assets, list):
        return None
    needle = pattern.strip().lower()
    for asset in assets:
        name = str(asset.get("name") or "")
        if needle and needle in name.lower():
            return asset
    return assets[0] if assets else None


def _repo(config: UpdateConfig) -> str:
    """Return the GitHub repo used for release updates."""
    return (config.repo or DEFAULT_UPDATE_REPO).strip()


def _asset_pattern(config: UpdateConfig) -> str:
    """Return the release asset name pattern."""
    return (config.asset_pattern or DEFAULT_ASSET_PATTERN).strip()


def _current_version(config: UpdateConfig, base_dir: Path | None) -> str:
    """Read the running app version from VERSION, falling back to config."""
    if base_dir is not None:
        for path in (base_dir / "VERSION", base_dir.parent / "VERSION", base_dir.parent / "sync" / "VERSION"):
            try:
                version = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if version:
                return _normalize_version(version)
    return _normalize_version(config.current_version or "0.0.0")


def _normalize_version(value: str) -> str:
    """Strip common version prefixes."""
    return value.strip().lstrip("vV")


def _version_tuple(value: str) -> tuple[int, ...]:
    """Convert a version string into a comparable tuple."""
    numbers = [int(part) for part in re.findall(r"\d+", _normalize_version(value))]
    return tuple(numbers or [0])


def _safe_filename(value: str) -> str:
    """Return a filesystem-safe filename."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" .") or "update.zip"


def _download_dir(config: UpdateConfig, base_dir: Path) -> Path:
    """Return the absolute update download directory."""
    download_dir = Path(config.download_dir)
    if download_dir.is_absolute():
        return download_dir
    return base_dir / download_dir


def _download_target_path(download_dir: Path, asset_name: str, latest_version: str | None) -> Path:
    """Return a stable, versioned path for a downloaded update asset."""
    safe_name = _safe_filename(asset_name)
    path = download_dir / safe_name
    version = _safe_filename(_normalize_version(latest_version or ""))
    if not version:
        return path
    if version.lower() in path.stem.lower():
        return path
    return path.with_name(f"{path.stem}-{version}{path.suffix}")


def _existing_download_path(
    config: UpdateConfig,
    base_dir: Path,
    asset_name: str,
    latest_version: str | None,
) -> Path | None:
    """Return a previously downloaded update asset for this version, if present."""
    target_path = _download_target_path(_download_dir(config, base_dir), asset_name, latest_version)
    if target_path.exists() and target_path.stat().st_size > 0:
        return target_path
    return None


def _is_portable_root(root: Path) -> bool:
    """Return whether a folder looks like the portable app root."""
    return (root / "run-portable.bat").exists() and (root / "python" / "python.exe").exists() and (root / "sync").is_dir()


def _env_int(name: str) -> int:
    """Return an integer environment variable, or 0 when it is absent/invalid."""
    try:
        return int(os.environ.get(name, "0") or "0")
    except ValueError:
        return 0


def _launcher_path_from_env() -> Path | None:
    """Return the current portable launcher path when the tray provided it."""
    value = os.environ.get("POWERBI_DTL_LAUNCHER", "").strip()
    return Path(value) if value else None


def _extract_update(zip_path: Path, base_dir: Path, version: str) -> Path:
    """Extract a release zip into a staging folder."""
    stage_parent = base_dir / "downloads" / "updates" / "_staged"
    stage_parent.mkdir(parents=True, exist_ok=True)
    stage_dir = stage_parent / f"{_safe_filename(version)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            _safe_extract_zip(archive, stage_dir)
    except zipfile.BadZipFile as exc:
        raise UpdateError(f"Update asset is not a valid zip file: {zip_path}") from exc
    return stage_dir


def _safe_extract_zip(archive: zipfile.ZipFile, target_dir: Path) -> None:
    """Extract a zip archive without allowing paths outside target_dir."""
    resolved_target = target_dir.resolve()
    for member in archive.infolist():
        member_path = (target_dir / member.filename).resolve()
        try:
            member_path.relative_to(resolved_target)
        except ValueError as exc:
            raise UpdateError("Update zip contains an unsafe path.") from exc
    archive.extractall(target_dir)


def _find_portable_root(stage_dir: Path) -> Path:
    """Find the app root inside an extracted portable zip."""
    candidates = [stage_dir, *[path for path in stage_dir.iterdir() if path.is_dir()]]
    for candidate in candidates:
        if (candidate / "run-portable.bat").exists() and (candidate / "sync" / "main.py").exists():
            return candidate
    raise UpdateError("The update zip does not contain a portable app root.")


def _write_apply_script(
    target_root: Path,
    source_root: Path,
    current_pid: int,
    version: str,
    *,
    tray_pid: int = 0,
    launcher_path: Path | None = None,
) -> Path:
    """Write a PowerShell script that applies the staged update after shutdown."""
    script_dir = target_root / "sync" / "downloads" / "updates"
    script_dir.mkdir(parents=True, exist_ok=True)
    script_path = script_dir / f"apply-update-{_safe_filename(version)}.ps1"
    log_path = script_dir / f"apply-update-{_safe_filename(version)}.log"
    source = str(source_root)
    target = str(target_root)
    launcher = str(launcher_path) if launcher_path else str(target_root / "run-portable.bat")
    script_path.write_text(
        _apply_script_text(
            source=source,
            target=target,
            log_path=str(log_path),
            current_pid=current_pid,
            tray_pid=tray_pid,
            launcher=launcher,
        ),
        encoding="utf-8",
    )
    return script_path


def _apply_script_text(
    *,
    source: str,
    target: str,
    log_path: str,
    current_pid: int,
    tray_pid: int,
    launcher: str,
) -> str:
    """Return the PowerShell script that swaps portable files and relaunches the app."""
    return f"""$ErrorActionPreference = "Stop"
$SourceRoot = @'
{source}
'@
$TargetRoot = @'
{target}
'@
$LogPath = @'
{log_path}
'@
$PidToWait = {current_pid}
$TrayPid = {tray_pid}
$LauncherPath = @'
{launcher}
'@
Start-Transcript -Path $LogPath -Append | Out-Null
try {{
  function Stop-ProcessById {{
    param(
      [int]$ProcessId,
      [string]$Label,
      [int]$TimeoutSeconds = 10
    )
    if ($ProcessId -le 0 -or $ProcessId -eq $PID) {{
      return
    }}
    $Process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $Process) {{
      return
    }}
    try {{
      Wait-Process -Id $ProcessId -Timeout $TimeoutSeconds -ErrorAction SilentlyContinue
    }} catch {{
    }}
    $Process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($Process) {{
      Write-Output "Stopping $Label process $ProcessId"
      Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }}
  }}

  function Stop-PortableProcesses {{
    $PythonRoot = (Join-Path $TargetRoot "python")
    $TargetPattern = "*" + $TargetRoot + "*"
    $Processes = Get-CimInstance Win32_Process | Where-Object {{
      ($_.ProcessId -ne $PID) -and (
        ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($PythonRoot, [System.StringComparison]::OrdinalIgnoreCase)) -or
        ($_.CommandLine -and $_.CommandLine -like "*run-portable.ps1*" -and $_.CommandLine -like $TargetPattern)
      )
    }}
    foreach ($Item in $Processes) {{
      Write-Output "Stopping portable process $($Item.ProcessId)"
      Stop-Process -Id $Item.ProcessId -Force -ErrorAction SilentlyContinue
    }}
  }}

  Stop-ProcessById -ProcessId $PidToWait -Label "API" -TimeoutSeconds 90
  Stop-ProcessById -ProcessId $TrayPid -Label "tray" -TimeoutSeconds 5
  Stop-PortableProcesses
  Start-Sleep -Seconds 2
  $ExcludedDirs = @(
    (Join-Path $SourceRoot "sync\\logs"),
    (Join-Path $SourceRoot "sync\\downloads"),
    (Join-Path $SourceRoot "sync\\uploads"),
    (Join-Path $SourceRoot "sync\\exports"),
    (Join-Path $SourceRoot "sync\\.preview_cache")
  )
  $RobocopyArgs = @($SourceRoot, $TargetRoot, "/E", "/R:3", "/W:2", "/XD") + $ExcludedDirs + @("/XF", "config.yaml", ".env", "*.pyc", "*.pyo")
  robocopy @RobocopyArgs | Out-Host
  $Code = $LASTEXITCODE
  if ($Code -ge 8) {{
    throw "Robocopy failed with exit code $Code"
  }}
  Start-Process $LauncherPath -WindowStyle Hidden
}} finally {{
  Stop-Transcript | Out-Null
}}
"""


def _launch_apply_script(script_path: Path) -> None:
    """Launch the apply script in a detached PowerShell process."""
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        windows_powershell = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        executable = str(windows_powershell) if windows_powershell.exists() else "powershell"
    else:
        executable = "pwsh" if shutil.which("pwsh") else "powershell"
    subprocess.Popen(
        [
            executable,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            str(script_path),
        ],
        cwd=str(script_path.parent),
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )


def _exit_process_soon(delay_seconds: float = 1.5) -> None:
    """Exit the current API process after the HTTP response is returned."""

    def worker() -> None:
        time.sleep(delay_seconds)
        LOGGER.info("Exiting process for self-update.")
        os._exit(0)

    thread = threading.Thread(target=worker, name="self-update-exit", daemon=True)
    thread.start()
