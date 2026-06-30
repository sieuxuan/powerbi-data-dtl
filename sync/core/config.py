"""Đọc và kiểm tra cấu hình YAML cho hệ thống đồng bộ."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
SUPPORTED_SOURCE_TYPES = {"local", "onedrive"}
SUPPORTED_SYNC_MODES = {"truncate_insert", "drop_recreate", "append", "upsert"}
SUPPORTED_MISMATCH_POLICIES = {"notify", "auto_recreate", "skip"}


class ConfigError(ValueError):
    """Raised when the sync configuration is invalid."""


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    name: str
    user: str
    password: str
    schema: str = "public"


@dataclass(frozen=True)
class ScheduleConfig:
    default_cron: str = "0 6 * * *"
    timezone: str = "Asia/Ho_Chi_Minh"
    on_startup: bool = True


@dataclass(frozen=True)
class SourceConfig:
    type: str
    path: str | None = None
    share_url: str | None = None
    download_url: str | None = None


@dataclass(frozen=True)
class TargetConfig:
    table: str
    schema: str | None = None
    primary_key: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FileOptions:
    sheet: int | str = 0
    header_row: int = 0
    skip_rows: list[int] | int | None = field(default_factory=list)
    usecols: str | list[str] | None = None
    skip_columns: list[str] = field(default_factory=list)
    encoding: str | None = "utf-8"
    delimiter: str | None = ","
    column_renames: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SyncFileConfig:
    name: str
    source: SourceConfig
    target: TargetConfig
    options: FileOptions = field(default_factory=FileOptions)
    sync_mode: str = "truncate_insert"
    on_column_mismatch: str = "notify"
    cron: str | None = None
    crons: list[str] = field(default_factory=list)
    enabled: bool = True
    skip_unchanged: bool = True


@dataclass(frozen=True)
class EmailConfig:
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    sender: str = ""
    password: str = ""
    recipients: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WebhookConfig:
    enabled: bool = False
    url: str = ""
    timeout_seconds: float = 15
    statuses: list[str] = field(default_factory=lambda: ["success", "failed", "mismatch"])


@dataclass(frozen=True)
class NotificationConfig:
    windows_toast: bool = False
    email: EmailConfig = field(default_factory=EmailConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    file_dir: str = "./logs"
    max_file_size_mb: int = 10
    backup_count: int = 30
    log_to_db: bool = True


@dataclass(frozen=True)
class DownloadsConfig:
    dir: str = "./downloads"
    keep_files: bool = False


@dataclass(frozen=True)
class UpdateConfig:
    enabled: bool = False
    repo: str = ""
    current_version: str = "0.0.0"
    asset_pattern: str = "PowerBIDataDTL-portable.zip"
    check_on_startup: bool = True
    auto_download: bool = False
    auto_apply: bool = False
    allow_prerelease: bool = False
    download_dir: str = "./downloads/updates"


@dataclass(frozen=True)
class ApiConfig:
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8765
    cors_origins: list[str] = field(
        default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"]
    )


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int
    delay_seconds: float


@dataclass(frozen=True)
class RetryConfig:
    db: RetryPolicy = field(default_factory=lambda: RetryPolicy(attempts=3, delay_seconds=10))
    file: RetryPolicy = field(default_factory=lambda: RetryPolicy(attempts=2, delay_seconds=2))
    onedrive: RetryPolicy = field(default_factory=lambda: RetryPolicy(attempts=3, delay_seconds=30))


@dataclass(frozen=True)
class MaintenanceConfig:
    enabled: bool = True
    sync_log_retention_days: int = 180
    downloads_retention_days: int = 14
    uploads_retention_days: int = 365
    preview_cache_retention_days: int = 3


@dataclass(frozen=True)
class AppConfig:
    database: DatabaseConfig
    schedule: ScheduleConfig
    files: list[SyncFileConfig]
    notifications: NotificationConfig
    logging: LoggingConfig
    downloads: DownloadsConfig
    updates: UpdateConfig
    api: ApiConfig
    retry: RetryConfig
    config_path: Path
    base_dir: Path
    maintenance: MaintenanceConfig = field(default_factory=MaintenanceConfig)


def load_config(path: str | Path) -> AppConfig:
    """Load, expand environment variables, and validate a YAML config file."""
    config_path = Path(path).resolve()
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")
    _load_dotenv(config_path.parent / ".env")

    try:
        import yaml
    except ImportError as exc:
        raise ConfigError("PyYAML is required. Install dependencies with: pip install -r requirements.txt") from exc

    raw_text = _expand_env_vars(config_path.read_text(encoding="utf-8"))
    raw = yaml.safe_load(raw_text) or {}
    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a YAML mapping.")

    database = _parse_database(_require_mapping(raw, "database"))
    schedule = _parse_schedule(_optional_mapping(raw, "schedule"))
    files = _parse_files(raw.get("files", []), database.schema)
    notifications = _parse_notifications(_optional_mapping(raw, "notifications"))
    logging_config = _parse_logging(_optional_mapping(raw, "logging"))
    downloads = _parse_downloads(_optional_mapping(raw, "downloads"))
    updates = _parse_updates(_optional_mapping(raw, "updates"))
    api = _parse_api(_optional_mapping(raw, "api"))
    retry = _parse_retry(_optional_mapping(raw, "retry"))
    maintenance = _parse_maintenance(_optional_mapping(raw, "maintenance"))

    return AppConfig(
        database=database,
        schedule=schedule,
        files=files,
        notifications=notifications,
        logging=logging_config,
        downloads=downloads,
        updates=updates,
        api=api,
        retry=retry,
        maintenance=maintenance,
        config_path=config_path,
        base_dir=config_path.parent,
    )


def enabled_files(config: AppConfig) -> list[SyncFileConfig]:
    """Return enabled sync file entries."""
    return [item for item in config.files if item.enabled]


def _expand_env_vars(text: str) -> str:
    """Replace ${VAR_NAME} placeholders with environment values."""

    def replace(match: re.Match[str]) -> str:
        return os.environ.get(match.group(1), "")

    return ENV_PATTERN.sub(replace, text)


def _load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines from a local .env file without overwriting real env vars."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _require_mapping(raw: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a required nested mapping from raw config."""
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"Missing or invalid mapping: {key}")
    return value


def _optional_mapping(raw: dict[str, Any], key: str) -> dict[str, Any]:
    """Return an optional nested mapping from raw config."""
    value = raw.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"Invalid mapping: {key}")
    return value


def _parse_database(raw: dict[str, Any]) -> DatabaseConfig:
    """Parse database config."""
    required = ("host", "name", "user")
    for key in required:
        if not raw.get(key):
            raise ConfigError(f"database.{key} is required")

    return DatabaseConfig(
        host=str(raw["host"]),
        port=int(raw.get("port", 5432)),
        name=str(raw["name"]),
        user=str(raw["user"]),
        password=str(raw.get("password", "")),
        schema=str(raw.get("schema", "public")),
    )


def _parse_schedule(raw: dict[str, Any]) -> ScheduleConfig:
    """Parse scheduler defaults."""
    return ScheduleConfig(
        default_cron=str(raw.get("default_cron", "0 6 * * *")),
        timezone=str(raw.get("timezone", "Asia/Ho_Chi_Minh")),
        on_startup=_as_bool(raw.get("on_startup", True)),
    )


def _parse_files(raw_files: Any, default_schema: str) -> list[SyncFileConfig]:
    """Parse file sync entries."""
    if raw_files is None:
        return []
    if not isinstance(raw_files, list):
        raise ConfigError("files must be a list")

    parsed: list[SyncFileConfig] = []
    for index, raw in enumerate(raw_files):
        prefix = f"files[{index}]"
        if not isinstance(raw, dict):
            raise ConfigError(f"{prefix} must be a mapping")

        name = str(raw.get("name") or "").strip()
        if not name:
            raise ConfigError(f"{prefix}.name is required")

        source = _parse_source(_require_mapping(raw, "source"), prefix)
        sync_mode = str(raw.get("sync_mode", "truncate_insert"))
        target = _parse_target(_require_mapping(raw, "target"), prefix, default_schema, sync_mode)
        options = _parse_options(_optional_mapping(raw, "options"))
        mismatch_policy = str(raw.get("on_column_mismatch", "notify"))

        if sync_mode not in SUPPORTED_SYNC_MODES:
            raise ConfigError(f"{prefix}.sync_mode must be one of {sorted(SUPPORTED_SYNC_MODES)}")
        if mismatch_policy not in SUPPORTED_MISMATCH_POLICIES:
            raise ConfigError(
                f"{prefix}.on_column_mismatch must be one of {sorted(SUPPORTED_MISMATCH_POLICIES)}"
            )

        parsed.append(
            SyncFileConfig(
                name=name,
                source=source,
                target=target,
                options=options,
                sync_mode=sync_mode,
                on_column_mismatch=mismatch_policy,
                cron=raw.get("cron"),
                crons=_parse_crons(raw),
                enabled=_as_bool(raw.get("enabled", True)),
                skip_unchanged=_as_bool(raw.get("skip_unchanged", True)),
            )
        )

    return parsed


def _parse_crons(raw: dict[str, Any]) -> list[str]:
    """Parse multiple job schedules while preserving the legacy cron field."""
    crons = _parse_string_list(raw.get("crons", []), "files[].crons")
    if crons:
        return crons
    legacy_cron = str(raw.get("cron") or "").strip()
    return [legacy_cron] if legacy_cron else []


def _parse_source(raw: dict[str, Any], prefix: str) -> SourceConfig:
    """Parse source config."""
    source_type = str(raw.get("type") or "").strip().lower()
    if source_type not in SUPPORTED_SOURCE_TYPES:
        raise ConfigError(f"{prefix}.source.type must be one of {sorted(SUPPORTED_SOURCE_TYPES)}")
    if source_type == "local" and not raw.get("path"):
        raise ConfigError(f"{prefix}.source.path is required for local sources")
    if source_type == "onedrive" and not (raw.get("share_url") or raw.get("download_url")):
        raise ConfigError(f"{prefix}.source.share_url or download_url is required for onedrive sources")

    return SourceConfig(
        type=source_type,
        path=str(raw["path"]) if raw.get("path") else None,
        share_url=str(raw["share_url"]) if raw.get("share_url") else None,
        download_url=str(raw["download_url"]) if raw.get("download_url") else None,
    )


def _parse_target(raw: dict[str, Any], prefix: str, default_schema: str, sync_mode: str) -> TargetConfig:
    """Parse target config."""
    table = str(raw.get("table") or "").strip()
    if not table:
        raise ConfigError(f"{prefix}.target.table is required")
    schema = str(raw.get("schema") or default_schema).strip()
    primary_key = _parse_string_list(raw.get("primary_key", []), f"{prefix}.target.primary_key")
    if sync_mode == "upsert" and not primary_key:
        raise ConfigError(f"{prefix}.target.primary_key is required when sync_mode is upsert")
    return TargetConfig(table=table, schema=schema, primary_key=primary_key)


def _parse_options(raw: dict[str, Any]) -> FileOptions:
    """Parse file reader options."""
    return FileOptions(
        sheet=0 if raw.get("sheet") is None else raw.get("sheet", 0),
        header_row=int(raw.get("header_row", 0)),
        skip_rows=raw.get("skip_rows", []),
        usecols=raw.get("usecols"),
        skip_columns=_parse_string_list(raw.get("skip_columns", []), "options.skip_columns"),
        encoding=raw.get("encoding", "utf-8"),
        delimiter=raw.get("delimiter", ","),
        column_renames=_parse_string_mapping(raw.get("column_renames", {}), "options.column_renames"),
    )


def _parse_notifications(raw: dict[str, Any]) -> NotificationConfig:
    """Parse notification config."""
    email_raw = raw.get("email", {}) or {}
    if not isinstance(email_raw, dict):
        raise ConfigError("notifications.email must be a mapping")
    webhook_raw = raw.get("webhook", {}) or {}
    if not isinstance(webhook_raw, dict):
        raise ConfigError("notifications.webhook must be a mapping")

    return NotificationConfig(
        windows_toast=_as_bool(raw.get("windows_toast", False)),
        email=EmailConfig(
            enabled=_as_bool(email_raw.get("enabled", False)),
            smtp_host=str(email_raw.get("smtp_host", "")),
            smtp_port=int(email_raw.get("smtp_port", 587)),
            sender=str(email_raw.get("sender", "")),
            password=str(email_raw.get("password", "")),
            recipients=_parse_string_list(email_raw.get("recipients", []), "notifications.email.recipients"),
        ),
        webhook=WebhookConfig(
            enabled=_as_bool(webhook_raw.get("enabled", False)),
            url=str(webhook_raw.get("url", "")).strip(),
            timeout_seconds=float(webhook_raw.get("timeout_seconds", 15)),
            statuses=_parse_string_list(
                webhook_raw.get("statuses", ["success", "failed", "mismatch"]),
                "notifications.webhook.statuses",
            ),
        ),
    )


def _parse_logging(raw: dict[str, Any]) -> LoggingConfig:
    """Parse logging config."""
    level = str(raw.get("level", "INFO")).upper()
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if level not in valid_levels:
        raise ConfigError(f"logging.level must be one of {sorted(valid_levels)}")

    return LoggingConfig(
        level=level,
        file_dir=str(raw.get("file_dir", "./logs")),
        max_file_size_mb=int(raw.get("max_file_size_mb", 10)),
        backup_count=int(raw.get("backup_count", 30)),
        log_to_db=_as_bool(raw.get("log_to_db", True)),
    )


def _parse_downloads(raw: dict[str, Any]) -> DownloadsConfig:
    """Parse download config."""
    return DownloadsConfig(
        dir=str(raw.get("dir", "./downloads")),
        keep_files=_as_bool(raw.get("keep_files", False)),
    )


def _parse_updates(raw: dict[str, Any]) -> UpdateConfig:
    """Parse GitHub release update settings."""
    return UpdateConfig(
        enabled=_as_bool(raw.get("enabled", False)),
        repo=str(raw.get("repo", "")).strip(),
        current_version=str(raw.get("current_version", "0.0.0")).strip() or "0.0.0",
        asset_pattern=str(raw.get("asset_pattern", "PowerBIDataDTL-portable.zip")).strip()
        or "PowerBIDataDTL-portable.zip",
        check_on_startup=_as_bool(raw.get("check_on_startup", True)),
        auto_download=_as_bool(raw.get("auto_download", False)),
        auto_apply=_as_bool(raw.get("auto_apply", False)),
        allow_prerelease=_as_bool(raw.get("allow_prerelease", False)),
        download_dir=str(raw.get("download_dir", "./downloads/updates")),
    )


def _parse_api(raw: dict[str, Any]) -> ApiConfig:
    """Parse local API config."""
    return ApiConfig(
        enabled=_as_bool(raw.get("enabled", True)),
        host=str(raw.get("host", "127.0.0.1")),
        port=int(raw.get("port", 8765)),
        cors_origins=_parse_string_list(
            raw.get("cors_origins", ["http://127.0.0.1:5173", "http://localhost:5173"]),
            "api.cors_origins",
        ),
    )


def _parse_retry(raw: dict[str, Any]) -> RetryConfig:
    """Parse retry policies."""
    return RetryConfig(
        db=_parse_retry_policy(raw.get("db", {}), "retry.db", 3, 10),
        file=_parse_retry_policy(raw.get("file", {}), "retry.file", 2, 2),
        onedrive=_parse_retry_policy(raw.get("onedrive", {}), "retry.onedrive", 3, 30),
    )


def _parse_maintenance(raw: dict[str, Any]) -> MaintenanceConfig:
    """Parse cleanup/retention settings."""
    return MaintenanceConfig(
        enabled=_as_bool(raw.get("enabled", True)),
        sync_log_retention_days=max(1, int(raw.get("sync_log_retention_days", 180))),
        downloads_retention_days=max(1, int(raw.get("downloads_retention_days", 14))),
        uploads_retention_days=max(1, int(raw.get("uploads_retention_days", 365))),
        preview_cache_retention_days=max(1, int(raw.get("preview_cache_retention_days", 3))),
    )


def _parse_retry_policy(raw: Any, prefix: str, attempts: int, delay_seconds: float) -> RetryPolicy:
    """Parse one retry policy."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{prefix} must be a mapping")
    parsed_attempts = int(raw.get("attempts", attempts))
    parsed_delay = float(raw.get("delay_seconds", delay_seconds))
    if parsed_attempts < 1:
        raise ConfigError(f"{prefix}.attempts must be at least 1")
    if parsed_delay < 0:
        raise ConfigError(f"{prefix}.delay_seconds must be >= 0")
    return RetryPolicy(attempts=parsed_attempts, delay_seconds=parsed_delay)


def _parse_string_list(value: Any, key: str) -> list[str]:
    """Parse a YAML string or list of strings into a list."""
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        raise ConfigError(f"{key} must be a string or list of strings")
    result = [str(item).strip() for item in value if str(item).strip()]
    if len(result) != len(set(result)):
        raise ConfigError(f"{key} must not contain duplicate values")
    return result


def _parse_string_mapping(value: Any, key: str) -> dict[str, str]:
    """Parse a YAML mapping into a string-to-string dictionary."""
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{key} must be a mapping")
    result: dict[str, str] = {}
    for raw_source, raw_target in value.items():
        source = str(raw_source).strip()
        target = str(raw_target).strip()
        if source and target:
            result[source] = target
    return result


def _as_bool(value: Any) -> bool:
    """Parse common YAML/env boolean values."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off", ""}:
            return False
    return bool(value)
