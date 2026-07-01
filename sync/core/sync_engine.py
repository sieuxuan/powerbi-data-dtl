"""Điều phối luồng đồng bộ: lấy file, so sánh schema, import, log và thông báo."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .config import AppConfig, SyncFileConfig, enabled_files
from .db import PostgresClient, validate_upsert_dataframe
from .file_reader import calculate_md5, read_tabular_file
from .notifier import Notifier
from .onedrive import DownloadResult, download_onedrive_file
from .retry import run_with_retry
from .schema_compare import compare_columns, normalize_dataframe_columns, normalize_identifier


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncResult:
    name: str
    table: str
    status: str
    rows_imported: int
    message: str
    started_at: datetime
    finished_at: datetime
    file_hash: str | None = None
    file_path: str | None = None
    error_message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary."""
        return {
            "name": self.name,
            "table": self.table,
            "status": self.status,
            "rows_imported": self.rows_imported,
            "message": self.message,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "file_hash": self.file_hash,
            "file_path": self.file_path,
            "error_message": self.error_message,
            "details": self.details,
        }


class SyncEngine:
    """Main coordinator for one-shot sync runs."""

    def __init__(self, config: AppConfig, progress_callback: Callable[[str, str], None] | None = None) -> None:
        self.config = config
        self.db = PostgresClient(config.database)
        self.notifier = Notifier(config.notifications)
        self.progress_callback = progress_callback

    def run_all(self, *, force: bool = False) -> list[SyncResult]:
        """Run all enabled sync jobs independently."""
        files = enabled_files(self.config)
        LOGGER.info("Found %s enabled sync job(s).", len(files))
        results: list[SyncResult] = []
        for file_config in files:
            results.append(self.run_one(file_config, force=force, send_summary=False))
        self.notifier.send_summary(results)
        return results

    def run_by_name(self, name: str, *, force: bool = False) -> SyncResult:
        """Run one sync job by configured name."""
        for file_config in self.config.files:
            if file_config.name == name:
                return self.run_one(file_config, force=force)
        raise ValueError(f"No sync file configured with name: {name}")

    def run_one(
        self,
        file_config: SyncFileConfig,
        *,
        force: bool = False,
        send_summary: bool = True,
    ) -> SyncResult:
        """Run one sync job and convert failures into a result."""
        started_at = datetime.now()
        table = normalize_identifier(file_config.target.table, "table")
        schema = normalize_identifier(file_config.target.schema or self.config.database.schema, "schema")
        primary_key = [normalize_identifier(column, "column") for column in file_config.target.primary_key]
        LOGGER.info("[%s] Starting sync into %s.%s", file_config.name, schema, table)
        self._progress(file_config.name, "starting")

        try:
            result = self._run_one(file_config, schema, table, primary_key, started_at, force=force)
            LOGGER.info("[%s] %s", file_config.name, result.message)
        except Exception as exc:
            LOGGER.exception("[%s] Sync failed.", file_config.name)
            result = SyncResult(
                name=file_config.name,
                table=f"{schema}.{table}",
                status="failed",
                rows_imported=0,
                message=str(exc),
                started_at=started_at,
                finished_at=datetime.now(),
                error_message=str(exc),
            )

        self._record_and_notify(result)
        self._progress(file_config.name, "done")
        if send_summary:
            self.notifier.send_summary([result])
        return result

    def list_jobs(self) -> list[dict[str, Any]]:
        """Return configured jobs enriched with latest sync log if available."""
        latest_logs = self._load_latest_logs()
        job_health = self._load_job_health()
        jobs: list[dict[str, Any]] = []
        for file_config in self.config.files:
            table = normalize_identifier(file_config.target.table, "table")
            schema = normalize_identifier(file_config.target.schema or self.config.database.schema, "schema")
            table_name = f"{schema}.{table}"
            latest = latest_logs.get((file_config.name, table_name))
            health = job_health.get((file_config.name, table_name), {})
            jobs.append(
                {
                    "name": file_config.name,
                    "enabled": file_config.enabled,
                    "source_type": file_config.source.type,
                    "table": table_name,
                    "sync_mode": file_config.sync_mode,
                    "cron": file_config.cron,
                    "crons": file_config.crons or ([file_config.cron] if file_config.cron else []),
                    "skip_unchanged": file_config.skip_unchanged,
                    "last_run": _json_safe_log(latest) if latest else None,
                    "health": health,
                }
            )
        return jobs

    def recent_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return recent sync logs."""
        if not self.config.logging.log_to_db:
            return []
        try:
            self.db.ensure_sync_log_table()
            logs = self.db.get_recent_logs(limit)
            return [_json_safe_log(row) for row in logs]
        except Exception as exc:
            LOGGER.info("Could not load recent sync logs for status view: %s", exc)
            return []

    def _run_one(
        self,
        file_config: SyncFileConfig,
        schema: str,
        table: str,
        primary_key: list[str],
        started_at: datetime,
        *,
        force: bool,
    ) -> SyncResult:
        """Execute one sync job."""
        if not file_config.enabled:
            return self._result(file_config, schema, table, "skipped", 0, "Job is disabled.", started_at)

        if self.config.logging.log_to_db:
            self._ensure_sync_log_table()
        self._run_cleanup()
        self._progress(file_config.name, "downloading" if file_config.source.type == "onedrive" else "resolving")
        source = self._prepare_source(file_config, table)
        try:
            self._progress(file_config.name, "hashing")
            file_hash = calculate_md5(source.path)
            file_path = str(source.path)
            if file_config.skip_unchanged and not force and self.config.logging.log_to_db:
                last_hash = self._db_call(
                    lambda: self.db.get_last_success_hash(file_config.name, f"{schema}.{table}"),
                    "load latest success hash",
                )
                if last_hash == file_hash:
                    return self._result(
                        file_config,
                        schema,
                        table,
                        "skipped",
                        0,
                        "File unchanged; import skipped.",
                        started_at,
                        {"reason": "unchanged"},
                        file_hash=file_hash,
                        file_path=file_path,
                    )

            self._progress(file_config.name, "reading")
            read_result = run_with_retry(
                lambda: read_tabular_file(source.path, file_config.options),
                self.config.retry.file,
                label=f"read file {file_config.name}",
                logger=LOGGER,
            )
            dataframe = normalize_dataframe_columns(read_result.dataframe)
            LOGGER.info(
                "[%s] Read %s rows, %s columns from %s",
                file_config.name,
                len(dataframe),
                len(dataframe.columns),
                read_result.file_path,
            )

            if not list(dataframe.columns):
                raise ValueError("Source file has no columns.")
            if file_config.sync_mode == "upsert":
                validate_upsert_dataframe(dataframe, primary_key)

            self._progress(file_config.name, "validating")
            table_exists = self._db_call(lambda: self.db.table_exists(schema, table), "check table existence")
            if not table_exists:
                self._progress(file_config.name, "importing")
                rows = self._replace_table(schema, table, dataframe, primary_key, file_config.sync_mode)
                return self._result(
                    file_config,
                    schema,
                    table,
                    "success",
                    rows,
                    f"Created table and imported {rows} row(s).",
                    started_at,
                    {"source_path": file_path},
                    file_hash=file_hash,
                    file_path=file_path,
                )

            compare_result = compare_columns(list(dataframe.columns), self._db_call(lambda: self.db.get_columns(schema, table), "load table schema"))
            if compare_result.has_mismatch:
                details = {
                    "missing_in_db": compare_result.missing_in_db,
                    "extra_in_db": compare_result.extra_in_db,
                    "source_path": file_path,
                }
                LOGGER.warning(
                    "[%s] Schema mismatch. missing_in_db=%s extra_in_db=%s",
                    file_config.name,
                    compare_result.missing_in_db,
                    compare_result.extra_in_db,
                )
                if file_config.on_column_mismatch == "auto_recreate":
                    self._progress(file_config.name, "importing")
                    rows = self._replace_table(schema, table, dataframe, primary_key, file_config.sync_mode)
                    return self._result(
                        file_config,
                        schema,
                        table,
                        "success",
                        rows,
                        f"Recreated table after schema mismatch and imported {rows} row(s).",
                        started_at,
                        details,
                        file_hash=file_hash,
                        file_path=file_path,
                    )
                status = "skipped" if file_config.on_column_mismatch == "skip" else "mismatch"
                message = (
                    "Schema mismatch skipped by policy."
                    if file_config.on_column_mismatch == "skip"
                    else "Schema mismatch; import skipped."
                )
                return self._result(
                    file_config,
                    schema,
                    table,
                    status,
                    0,
                    message,
                    started_at,
                    details,
                    file_hash=file_hash,
                    file_path=file_path,
                )

            self._progress(file_config.name, "importing")
            if file_config.sync_mode == "truncate_insert":
                rows = self._db_call(lambda: self.db.truncate_insert(schema, table, dataframe), "truncate and insert")
                message = f"Truncated table and imported {rows} row(s)."
            elif file_config.sync_mode == "drop_recreate":
                rows = self._replace_table(schema, table, dataframe, primary_key, file_config.sync_mode)
                message = f"Recreated table and imported {rows} row(s)."
            elif file_config.sync_mode == "append":
                rows = self._db_call(lambda: self.db.append_insert(schema, table, dataframe), "append rows")
                message = f"Appended {rows} row(s)."
            elif file_config.sync_mode == "upsert":
                rows = self._db_call(lambda: self.db.upsert_insert(schema, table, dataframe, primary_key), "upsert rows")
                message = f"Upserted {rows} row(s)."
            else:
                raise NotImplementedError(f"Unsupported sync mode: {file_config.sync_mode}")

            return self._result(
                file_config,
                schema,
                table,
                "success",
                rows,
                message,
                started_at,
                {"source_path": file_path},
                file_hash=file_hash,
                file_path=file_path,
            )
        finally:
            if source.temporary:
                try:
                    source.path.unlink(missing_ok=True)
                except OSError as exc:
                    LOGGER.warning("Could not remove temporary download %s: %s", source.path, exc)

    def _prepare_source(self, file_config: SyncFileConfig, table: str) -> DownloadResult:
        """Resolve or download the source file."""
        if file_config.source.type == "local":
            if not file_config.source.path:
                raise ValueError("Local source path is required.")
            return DownloadResult(path=_resolve_source_path(file_config.source.path, self.config.base_dir), temporary=False)
        if file_config.source.type == "onedrive":
            return run_with_retry(
                lambda: download_onedrive_file(file_config.source, self.config.downloads, self.config.base_dir, table),
                self.config.retry.onedrive,
                label=f"download OneDrive file {file_config.name}",
                logger=LOGGER,
            )
        raise NotImplementedError(f"Unsupported source type: {file_config.source.type}")

    def _replace_table(
        self,
        schema: str,
        table: str,
        dataframe: Any,
        primary_key: list[str],
        sync_mode: str,
    ) -> int:
        """Replace a target table and preserve upsert conflict keys when needed."""
        unique_columns = primary_key if sync_mode == "upsert" else None
        return self._db_call(
            lambda: self.db.replace_table(schema, table, dataframe, unique_columns),
            "replace table",
        )

    def _ensure_sync_log_table(self) -> None:
        """Ensure sync_log exists."""
        self._db_call(self.db.ensure_sync_log_table, "ensure sync_log table")

    def _db_call(self, operation: Any, label: str) -> Any:
        """Run a database operation with retry."""
        return run_with_retry(operation, self.config.retry.db, label=label, logger=LOGGER)

    def _record_and_notify(self, result: SyncResult) -> None:
        """Persist and notify a result without masking the sync outcome."""
        if not self.config.logging.log_to_db:
            self.notifier.notify_result(result)
            return
        try:
            self._ensure_sync_log_table()
            self._db_call(
                lambda: self.db.insert_sync_log(
                    job_name=result.name,
                    table_name=result.table,
                    started_at=result.started_at,
                    finished_at=result.finished_at,
                    status=result.status,
                    rows_imported=result.rows_imported,
                    file_hash=result.file_hash,
                    file_path=result.file_path,
                    error_message=result.error_message,
                    details=result.details,
                ),
                "insert sync log",
            )
        except Exception as exc:
            LOGGER.warning("Could not write sync_log for %s: %s", result.name, exc)

        self.notifier.notify_result(result)

    def _run_cleanup(self) -> None:
        """Best-effort cleanup for sync_log and local cache folders."""
        if not self.config.maintenance.enabled:
            return
        if self.config.logging.log_to_db:
            try:
                self._db_call(
                    lambda: self.db.cleanup_sync_log(self.config.maintenance.sync_log_retention_days),
                    "cleanup sync_log",
                )
            except Exception as exc:
                LOGGER.info("Could not cleanup sync_log: %s", exc)
        _cleanup_folder(_resolve_source_path(self.config.downloads.dir, self.config.base_dir), self.config.maintenance.downloads_retention_days)
        _cleanup_folder(self.config.base_dir / "uploads", self.config.maintenance.uploads_retention_days)
        _cleanup_folder(self.config.base_dir / ".preview_cache", self.config.maintenance.preview_cache_retention_days)

    def _progress(self, job_name: str, state: str) -> None:
        """Publish best-effort progress state."""
        if self.progress_callback is None:
            return
        try:
            self.progress_callback(job_name, state)
        except Exception as exc:
            LOGGER.debug("Progress callback failed for %s=%s: %s", job_name, state, exc)

    def _load_latest_logs(self) -> dict[tuple[str, str], dict[str, Any]]:
        """Load latest logs if the database is reachable."""
        if not self.config.logging.log_to_db:
            return {}
        try:
            self.db.ensure_sync_log_table()
            return self.db.get_latest_job_logs()
        except Exception as exc:
            LOGGER.info("Could not load latest job logs for status view: %s", exc)
            return {}

    def _load_job_health(self) -> dict[tuple[str, str], dict[str, Any]]:
        """Compute lightweight per-job health metrics from recent sync_log rows."""
        if not self.config.logging.log_to_db:
            return {}
        try:
            self.db.ensure_sync_log_table()
            rows = self.db.get_job_log_history()
        except Exception as exc:
            LOGGER.info("Could not load job health metrics: %s", exc)
            return {}

        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault((row["job_name"], row["table_name"]), []).append(row)

        health: dict[tuple[str, str], dict[str, Any]] = {}
        for key, history in grouped.items():
            durations = [_duration_seconds(row) for row in history]
            durations = [value for value in durations if value is not None]
            success_rows = [row for row in history if row.get("status") == "success"]
            failure_streak = 0
            for row in history:
                if row.get("status") == "failed":
                    failure_streak += 1
                    continue
                break
            health[key] = {
                "last_duration_seconds": _duration_seconds(history[0]),
                "avg_duration_seconds": round(sum(durations) / len(durations), 2) if durations else None,
                "failure_streak": failure_streak,
                "last_success_rows": success_rows[0].get("rows_imported") if success_rows else None,
                "run_count": len(history),
            }
        return health

    @staticmethod
    def _result(
        file_config: SyncFileConfig,
        schema: str,
        table: str,
        status: str,
        rows_imported: int,
        message: str,
        started_at: datetime,
        details: dict[str, Any] | None = None,
        *,
        file_hash: str | None = None,
        file_path: str | None = None,
    ) -> SyncResult:
        """Build a SyncResult."""
        error_message = message if status == "failed" else None
        return SyncResult(
            name=file_config.name,
            table=f"{schema}.{table}",
            status=status,
            rows_imported=rows_imported,
            message=message,
            started_at=started_at,
            finished_at=datetime.now(),
            file_hash=file_hash,
            file_path=file_path,
            error_message=error_message,
            details=details or {},
        )


def _resolve_source_path(path: str, base_dir: Path) -> Path:
    """Resolve local file paths relative to the config file directory."""
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate.resolve()


def _cleanup_folder(path: Path, retention_days: int) -> None:
    """Delete old files from a folder while preserving .gitkeep files."""
    if not path.exists() or not path.is_dir():
        return
    cutoff = time.time() - retention_days * 86400
    for item in path.rglob("*"):
        try:
            if item.is_file() and item.name != ".gitkeep" and item.stat().st_mtime < cutoff:
                item.unlink()
        except OSError as exc:
            LOGGER.debug("Could not cleanup %s: %s", item, exc)


def _duration_seconds(row: dict[str, Any]) -> float | None:
    """Return a sync_log duration in seconds when both timestamps are present."""
    started_at = row.get("started_at")
    finished_at = row.get("finished_at")
    if not started_at or not finished_at:
        return None
    try:
        return max(0.0, round((finished_at - started_at).total_seconds(), 2))
    except AttributeError:
        return None


def _json_safe_log(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert datetime fields in a log row to ISO strings."""
    if row is None:
        return None
    result = dict(row)
    for key in ("started_at", "finished_at"):
        value = result.get(key)
        if isinstance(value, datetime):
            result[key] = value.isoformat()
    return result
