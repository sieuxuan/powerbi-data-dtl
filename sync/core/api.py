"""FastAPI localhost API cho dashboard Sync Monitor."""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import AppConfig, ConfigError, SourceConfig, load_config
from .db import PostgresClient, infer_dataframe_schema, validate_upsert_dataframe
from .file_reader import calculate_md5, read_tabular_file
from .notifier import Notifier
from .onedrive import _filename_from_url, _source_kind, download_onedrive_file
from .schema_compare import compare_columns, normalize_dataframe_columns, normalize_identifier
from .sync_engine import SyncEngine
from .updater import UpdateError, apply_update, check_for_update, download_update


LOGGER = logging.getLogger(__name__)
SAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


class ApiJobRunner:
    """Tracks background API-triggered runs and prevents duplicates."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.lock = threading.Lock()
        self.running: set[str] = set()
        self.progress: dict[str, dict[str, Any]] = {}

    def is_running(self, name: str) -> bool:
        """Return whether a job is currently running."""
        with self.lock:
            return name in self.running or "__all__" in self.running

    def running_names(self) -> set[str]:
        """Return a snapshot of running job names."""
        with self.lock:
            return set(self.running)

    def progress_snapshot(self) -> dict[str, dict[str, Any]]:
        """Return current progress by job name."""
        with self.lock:
            return dict(self.progress)

    def set_progress(self, name: str, state: str) -> None:
        """Store the latest progress state for a job."""
        with self.lock:
            self.progress[name] = {"state": state, "updated_at": datetime.now().isoformat()}

    def schedule_one(self, background_tasks: Any, name: str, force: bool) -> bool:
        """Schedule one job if it is not already running."""
        with self.lock:
            if name in self.running or "__all__" in self.running:
                return False
            self.running.add(name)

        def task() -> None:
            try:
                SyncEngine(load_config(self.config_path), progress_callback=self.set_progress).run_by_name(name, force=force)
            finally:
                with self.lock:
                    self.running.discard(name)

        background_tasks.add_task(task)
        return True

    def schedule_all(self, background_tasks: Any, force: bool) -> bool:
        """Schedule all jobs if no API-triggered run is active."""
        with self.lock:
            if self.running:
                return False
            self.running.add("__all__")

        def task() -> None:
            try:
                SyncEngine(load_config(self.config_path), progress_callback=self.set_progress).run_all(force=force)
            finally:
                with self.lock:
                    self.running.discard("__all__")

        background_tasks.add_task(task)
        return True


def create_app(config: AppConfig, runtime_status: Any | None = None) -> Any:
    """Create the FastAPI app."""
    try:
        from fastapi import BackgroundTasks, FastAPI, HTTPException
        from fastapi.responses import FileResponse
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise RuntimeError("FastAPI is required. Install dependencies with: pip install -r requirements.txt") from exc
    globals()["BackgroundTasks"] = BackgroundTasks

    config_path = config.config_path
    preview_cache_lock = threading.Lock()
    preview_source_cache: dict[str, Path] = {}
    preview_result_cache: dict[str, dict[str, Any]] = {}

    def read_runtime_config() -> AppConfig:
        try:
            return load_config(config_path)
        except ConfigError as exc:
            raise HTTPException(status_code=500, detail=f"Invalid sync config: {exc}") from exc

    def read_config_yaml() -> dict[str, Any]:
        try:
            import yaml
        except ImportError as exc:
            raise HTTPException(status_code=500, detail="PyYAML is required") from exc
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise HTTPException(status_code=500, detail="Config root must be a YAML mapping")
        return data

    def validate_config_payload(payload: dict[str, Any]) -> None:
        load_payload_config(payload)

    def load_payload_config(payload: dict[str, Any]) -> AppConfig:
        try:
            import yaml
        except ImportError as exc:
            raise HTTPException(status_code=500, detail="PyYAML is required") from exc

        temp_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".yaml",
                prefix=".config-check-",
                dir=config_path.parent,
                delete=False,
            ) as temp_file:
                yaml.safe_dump(payload, temp_file, allow_unicode=True, sort_keys=False)
                temp_name = temp_file.name
            return load_config(temp_name)
        except ConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            if temp_name:
                Path(temp_name).unlink(missing_ok=True)

    def config_payload_from_request(payload: dict[str, Any] | None) -> dict[str, Any]:
        if payload and isinstance(payload.get("config"), dict):
            return payload["config"]
        if payload and "database" in payload:
            return payload
        return read_config_yaml()

    def write_config_yaml(payload: dict[str, Any]) -> Path:
        try:
            import yaml
        except ImportError as exc:
            raise HTTPException(status_code=500, detail="PyYAML is required") from exc
        backup_path = config_path.with_suffix(f"{config_path.suffix}.bak")
        if config_path.exists():
            shutil.copy2(config_path, backup_path)
        config_path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return backup_path

    def unique_upload_path(filename: str) -> Path:
        upload_dir = config_path.parent / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        sanitized = SAFE_FILENAME.sub("_", Path(filename).name).strip(" .")
        if not sanitized:
            sanitized = "upload.xlsx"
        target = upload_dir / sanitized
        if not target.exists():
            return target
        for index in range(2, 10_000):
            candidate = upload_dir / f"{target.stem}_{index}{target.suffix}"
            if not candidate.exists():
                return candidate
        raise HTTPException(status_code=500, detail="Could not allocate upload filename")

    def prepare_file_from_payload(payload: dict[str, Any]) -> tuple[AppConfig, Any, Any]:
        file_payload = payload.get("file")
        if not isinstance(file_payload, dict):
            raise HTTPException(status_code=400, detail="file payload is required")
        config_payload = dict(config_payload_from_request(payload))
        config_payload["files"] = [file_payload]
        runtime_config = load_payload_config(config_payload)
        file_config = runtime_config.files[0]
        source = SyncEngine(runtime_config)._prepare_source(file_config, file_config.target.table)
        return runtime_config, file_config, source

    def prepare_preview_file_from_payload(payload: dict[str, Any]) -> tuple[AppConfig, Any, Any, str]:
        """Prepare a file for preview, reusing cached SharePoint downloads."""
        from .onedrive import DownloadResult

        file_payload = payload.get("file")
        if not isinstance(file_payload, dict):
            raise HTTPException(status_code=400, detail="file payload is required")
        config_payload = dict(config_payload_from_request(payload))
        config_payload["files"] = [file_payload]
        runtime_config = load_payload_config(config_payload)
        file_config = runtime_config.files[0]
        if file_config.source.type != "onedrive":
            source = SyncEngine(runtime_config)._prepare_source(file_config, file_config.target.table)
            file_hash = calculate_md5(source.path)
            return runtime_config, file_config, source, file_hash

        source_key = hashlib.sha256(
            (file_config.source.download_url or file_config.source.share_url or "").encode("utf-8")
        ).hexdigest()
        with preview_cache_lock:
            cached_path = preview_source_cache.get(source_key)
            if cached_path and cached_path.exists():
                file_hash = calculate_md5(cached_path)
                return runtime_config, file_config, DownloadResult(path=cached_path, temporary=False), file_hash

        source = SyncEngine(runtime_config)._prepare_source(file_config, file_config.target.table)
        file_hash = calculate_md5(source.path)
        cache_dir = config_path.parent / ".preview_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached_path = cache_dir / f"{file_hash}{source.path.suffix or '.xlsx'}"
        if not cached_path.exists():
            shutil.copy2(source.path, cached_path)
        if source.temporary:
            source.path.unlink(missing_ok=True)
        with preview_cache_lock:
            preview_source_cache[source_key] = cached_path
        return runtime_config, file_config, DownloadResult(path=cached_path, temporary=False), file_hash

    def build_export_bundle(include_uploads: bool) -> Path:
        export_dir = config_path.parent / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        export_path = export_dir / f"powerbi-data-dtl-config-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
        with zipfile.ZipFile(export_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if config_path.exists():
                archive.write(config_path, "sync/config.yaml")
            env_path = config_path.parent / ".env"
            if env_path.exists():
                archive.write(env_path, "sync/.env")
            for folder_name in ("downloads", "logs"):
                keep_path = config_path.parent / folder_name / ".gitkeep"
                if keep_path.exists():
                    archive.write(keep_path, f"sync/{folder_name}/.gitkeep")
            uploads_dir = config_path.parent / "uploads"
            if include_uploads and uploads_dir.exists():
                for path in uploads_dir.rglob("*"):
                    if path.is_file():
                        archive.write(path, f"sync/uploads/{path.relative_to(uploads_dir).as_posix()}")
            readme = (
                "PowerBI Data DTL config bundle\n\n"
                "Restore by copying sync/config.yaml, sync/.env, and sync/uploads into another project copy.\n"
                "Run run.bat or run.ps1 after restoring.\n"
            )
            archive.writestr("RESTORE.txt", readme)
        return export_path

    def restore_export_bundle(content: bytes) -> dict[str, Any]:
        """Restore config.yaml, .env, and uploads from an exported zip bundle."""
        restored_uploads = 0
        with tempfile.TemporaryDirectory(dir=config_path.parent) as temp_dir:
            temp_path = Path(temp_dir)
            zip_path = temp_path / "bundle.zip"
            zip_path.write_bytes(content)
            try:
                with zipfile.ZipFile(zip_path) as archive:
                    _safe_extract_bundle(archive, temp_path / "extract")
            except zipfile.BadZipFile as exc:
                raise HTTPException(status_code=400, detail="Invalid zip bundle") from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            extract_dir = temp_path / "extract"
            bundle_config = _first_existing(
                extract_dir / "sync" / "config.yaml",
                extract_dir / "config.yaml",
            )
            if not bundle_config:
                raise HTTPException(status_code=400, detail="Bundle does not contain sync/config.yaml")
            try:
                load_config(bundle_config)
            except ConfigError as exc:
                raise HTTPException(status_code=400, detail=f"Bundle config is invalid: {exc}") from exc

            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            if config_path.exists():
                shutil.copy2(config_path, config_path.with_suffix(f"{config_path.suffix}.before-import-{timestamp}.bak"))
            shutil.copy2(bundle_config, config_path)

            bundle_env = _first_existing(extract_dir / "sync" / ".env", extract_dir / ".env")
            if bundle_env:
                env_path = config_path.parent / ".env"
                if env_path.exists():
                    shutil.copy2(env_path, env_path.with_suffix(f"{env_path.suffix}.before-import-{timestamp}.bak"))
                shutil.copy2(bundle_env, env_path)

            bundle_uploads = extract_dir / "sync" / "uploads"
            if bundle_uploads.exists():
                uploads_dir = config_path.parent / "uploads"
                uploads_dir.mkdir(parents=True, exist_ok=True)
                for path in bundle_uploads.rglob("*"):
                    if path.is_file():
                        target = uploads_dir / path.relative_to(bundle_uploads)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(path, target)
                        restored_uploads += 1

        return {"status": "imported", "uploads": restored_uploads, "path": str(config_path)}

    def preview_export_bundle(content: bytes) -> dict[str, Any]:
        """Inspect an exported config bundle without restoring it."""
        with tempfile.TemporaryDirectory(dir=config_path.parent) as temp_dir:
            temp_path = Path(temp_dir)
            zip_path = temp_path / "bundle.zip"
            zip_path.write_bytes(content)
            try:
                with zipfile.ZipFile(zip_path) as archive:
                    names = archive.namelist()
                    _safe_extract_bundle(archive, temp_path / "extract")
            except zipfile.BadZipFile as exc:
                raise HTTPException(status_code=400, detail="Invalid zip bundle") from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            extract_dir = temp_path / "extract"
            bundle_config = _first_existing(extract_dir / "sync" / "config.yaml", extract_dir / "config.yaml")
            summary: dict[str, Any] = {
                "status": "ok",
                "has_config": bool(bundle_config),
                "has_env": bool(_first_existing(extract_dir / "sync" / ".env", extract_dir / ".env")),
                "uploads_count": len([name for name in names if name.startswith("sync/uploads/") and not name.endswith("/")]),
                "files_count": len([name for name in names if not name.endswith("/")]),
            }
            if bundle_config:
                try:
                    bundle_runtime = load_config(bundle_config)
                    summary["jobs_count"] = len(bundle_runtime.files)
                    summary["database"] = {
                        "host": bundle_runtime.database.host,
                        "name": bundle_runtime.database.name,
                        "schema": bundle_runtime.database.schema,
                    }
                except ConfigError as exc:
                    summary["config_error"] = str(exc)
            return summary

    def dry_run_file_payload(payload: dict[str, Any]) -> dict[str, Any]:
        """Read and validate a file job without importing rows."""
        runtime_config, file_config, source, _file_hash = prepare_preview_file_from_payload(payload)
        schema = normalize_identifier(file_config.target.schema or runtime_config.database.schema, "schema")
        table = normalize_identifier(file_config.target.table, "table")
        primary_key = [normalize_identifier(column, "column") for column in file_config.target.primary_key]
        try:
            sample_limit = int(payload.get("sample_rows") or 1000)
            read_result = read_tabular_file(source.path, file_config.options, nrows=max(20, min(sample_limit, 5000)))
            dataframe = normalize_dataframe_columns(read_result.dataframe)
            db_client = PostgresClient(runtime_config.database)
            db_client.test_write_permission(schema)
            table_exists = db_client.table_exists(schema, table)
            db_columns = db_client.get_columns(schema, table) if table_exists else None
            compare_result = compare_columns(list(dataframe.columns), db_columns)
            if file_config.sync_mode == "upsert":
                validate_upsert_dataframe(dataframe, primary_key)
            return {
                "status": "ok",
                "job": file_config.name,
                "target": f"{schema}.{table}",
                "source_path": str(read_result.file_path),
                "hash": read_result.file_hash,
                "rows": read_result.row_count,
                "sampled": True,
                "sample_limit": sample_limit,
                "columns": infer_dataframe_schema(dataframe),
                "table_exists": table_exists,
                "schema_match": compare_result.match,
                "missing_in_db": compare_result.missing_in_db,
                "extra_in_db": compare_result.extra_in_db,
                "message": "Dry run OK on a sample. No rows were imported.",
            }
        finally:
            if source.temporary:
                source.path.unlink(missing_ok=True)

    def app_folder_path(folder: str) -> Path:
        """Return a whitelisted app folder path."""
        runtime_config = read_runtime_config()
        key = folder.strip().lower()
        paths = {
            "config": config_path.parent,
            "uploads": config_path.parent / "uploads",
            "downloads": _resolve_configured_dir(config_path.parent, runtime_config.downloads.dir),
            "logs": _resolve_configured_dir(config_path.parent, runtime_config.logging.file_dir),
            "exports": config_path.parent / "exports",
        }
        if key not in paths:
            raise HTTPException(status_code=400, detail="folder must be one of: config, uploads, downloads, logs, exports")
        return paths[key].resolve()

    def open_folder_in_shell(path: Path) -> None:
        """Open a folder in the operating system file manager."""
        path.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                # os.startfile reliably opens Explorer and brings it to the foreground;
                # explorer.exe via Popen is flaky about focus and path handling.
                os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
            elif os.name == "posix":
                subprocess.Popen(["xdg-open", str(path)])
            else:
                raise RuntimeError(f"Unsupported OS for opening folders: {os.name}")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Could not open folder: {exc}") from exc

    def preview_tabular_file(path: Path, file_config: Any) -> dict[str, Any]:
        try:
            import pandas as pd
        except ImportError as exc:
            raise HTTPException(status_code=500, detail="pandas is required") from exc

        extension = path.suffix.lower()
        if extension in {".csv", ".tsv"}:
            delimiter = file_config.options.delimiter
            if extension == ".tsv" and (delimiter is None or delimiter == ","):
                delimiter = "\t"
            preview_df = pd.read_csv(
                path,
                encoding=file_config.options.encoding or "utf-8",
                sep=delimiter or ",",
                header=None,
                nrows=20,
            )
            rows = _dataframe_preview_rows(preview_df)
            return {
                "status": "ok",
                "path": str(path),
                "type": "csv",
                "sheets": [
                    {
                        "name": "CSV",
                        "index": 0,
                        "suggested_header_row": _suggest_header_row(rows),
                        "rows": rows,
                    }
                ],
            }

        try:
            excel = pd.ExcelFile(path, engine="calamine")
        except Exception:
            excel = pd.ExcelFile(path)
        sheets: list[dict[str, Any]] = []
        for index, sheet_name in enumerate(excel.sheet_names):
            preview_df = pd.read_excel(excel, sheet_name=sheet_name, header=None, nrows=20)
            rows = _dataframe_preview_rows(preview_df)
            sheets.append(
                {
                    "name": sheet_name,
                    "index": index,
                    "suggested_header_row": _suggest_header_row(rows),
                    "rows": rows,
                }
            )
        return {"status": "ok", "path": str(path), "type": "excel", "sheets": sheets}

    def cached_preview_tabular_file(path: Path, file_config: Any, file_hash: str) -> dict[str, Any]:
        """Return cached tabular preview for a file hash and reader options."""
        cache_key = "|".join(
            [
                file_hash,
                str(file_config.options.sheet),
                str(file_config.options.header_row),
                str(file_config.options.delimiter),
                str(file_config.options.encoding),
            ]
        )
        with preview_cache_lock:
            cached = preview_result_cache.get(cache_key)
            if cached:
                return dict(cached)
        result = preview_tabular_file(path, file_config)
        result["file_hash"] = file_hash
        with preview_cache_lock:
            preview_result_cache[cache_key] = dict(result)
        return result

    app = FastAPI(title="PowerBI Data DTL Sync API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.api.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    runner = ApiJobRunner(config_path)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        scheduler_status = runtime_status() if callable(runtime_status) else {
            "enabled": False,
            "running": False,
            "scheduled_jobs": 0,
            "next_runs": [],
            "message": "Scheduler is not attached. Start with python main.py start for automatic jobs.",
        }
        return {
            "status": "ok",
            "api": "sync",
            "config_path": str(config_path),
            "running": sorted(runner.running_names()),
            "scheduler": scheduler_status,
        }

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        return {"path": str(config_path), "config": read_config_yaml()}

    @app.post("/api/config")
    def save_config(payload: dict[str, Any]) -> dict[str, Any]:
        config_payload = config_payload_from_request(payload)
        if not isinstance(config_payload, dict):
            raise HTTPException(status_code=400, detail="Config payload must be an object")
        validate_config_payload(config_payload)
        backup_path = write_config_yaml(config_payload)
        return {
            "status": "saved",
            "path": str(config_path),
            "backup_path": str(backup_path),
            "restart_required": False,
            "message": "Config saved. Scheduler will auto-reload cron changes while the sync runtime is running.",
        }

    @app.post("/api/config/test-db")
    def test_database(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        config_payload = dict(config_payload_from_request(payload))
        config_payload["files"] = []
        runtime_config = load_payload_config(config_payload)
        try:
            PostgresClient(runtime_config.database).test_connection()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "status": "ok",
            "message": (
                f"Connected to PostgreSQL {runtime_config.database.host}:"
                f"{runtime_config.database.port}/{runtime_config.database.name}."
            ),
        }

    @app.post("/api/config/test-write")
    def test_write_permission(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        config_payload = dict(config_payload_from_request(payload))
        config_payload["files"] = []
        runtime_config = load_payload_config(config_payload)
        schema = str((payload or {}).get("schema") or runtime_config.database.schema)
        try:
            PostgresClient(runtime_config.database).test_write_permission(schema)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "ok", "message": f"User can create, insert, and drop a test table in schema {schema}."}

    @app.post("/api/config/test-webhook")
    def test_webhook(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        config_payload = dict(config_payload_from_request(payload))
        config_payload["files"] = []
        runtime_config = load_payload_config(config_payload)
        test_payload = {
            "type": "sync_test",
            "job": "Webhook test",
            "table": "public.test_table",
            "status": "test",
            "rows_imported": 123,
            "message": "Webhook test from local Sync API.",
            "result": {
                "status": "test",
                "job": "Webhook test",
                "name": "PowerBI Data DTL",
                "table": "public.test_table",
                "rows_imported": 123,
                "message": "Webhook test from local Sync API.",
                "sent_at": datetime.now().isoformat(),
            },
        }
        try:
            Notifier(runtime_config.notifications).send_webhook_payload(test_payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "ok", "message": "Webhook test sent."}

    @app.post("/api/config/test-file")
    def test_file(payload: dict[str, Any]) -> dict[str, Any]:
        _runtime_config, file_config, source = prepare_file_from_payload(payload)
        try:
            read_result = read_tabular_file(source.path, file_config.options)
            return {
                "status": "ok",
                "message": (
                    f"Read {read_result.row_count} row(s), "
                    f"{len(read_result.columns)} column(s) from {read_result.file_path}."
                ),
                "path": str(read_result.file_path),
                "hash": read_result.file_hash,
                "rows": read_result.row_count,
                "columns": read_result.columns[:100],
                "column_count": len(read_result.columns),
            }
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            if source.temporary:
                source.path.unlink(missing_ok=True)

    @app.post("/api/config/dry-run-file")
    def dry_run_file(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return dry_run_file_payload(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/config/preview-file")
    def preview_file(payload: dict[str, Any]) -> dict[str, Any]:
        _runtime_config, file_config, source, file_hash = prepare_preview_file_from_payload(payload)
        try:
            return cached_preview_tabular_file(source.path, file_config, file_hash)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            if source.temporary:
                source.path.unlink(missing_ok=True)

    @app.post("/api/files/upload")
    def upload_file(payload: dict[str, Any]) -> dict[str, Any]:
        filename = str(payload.get("filename") or "").strip()
        content_base64 = str(payload.get("content_base64") or "")
        if "," in content_base64 and content_base64.lstrip().startswith("data:"):
            content_base64 = content_base64.split(",", 1)[1]
        if not filename or not content_base64:
            raise HTTPException(status_code=400, detail="filename and content_base64 are required")
        try:
            content = base64.b64decode(content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid base64 file content") from exc
        target_path = unique_upload_path(filename)
        target_path.write_bytes(content)
        relative_path = f"./uploads/{target_path.name}"
        return {
            "status": "ok",
            "path": relative_path,
            "absolute_path": str(target_path),
            "filename": target_path.name,
            "size": len(content),
        }

    @app.post("/api/files/fetch-link")
    def fetch_link(payload: dict[str, Any]) -> dict[str, Any]:
        url = str(payload.get("url") or "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="url is required")
        runtime_config = read_runtime_config()
        source = SourceConfig(type="onedrive", share_url=url)
        try:
            result = download_onedrive_file(source, runtime_config.downloads, runtime_config.base_dir, "linked_import")
            content = result.path.read_bytes()
            filename = result.path.name or _filename_from_url(url) or "linked_import.xlsx"
            return {
                "status": "ok",
                "filename": filename,
                "path": str(result.path),
                "size": len(content),
                "source_kind": _source_kind(url),
                "content_base64": base64.b64encode(content).decode("ascii"),
            }
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            if "result" in locals() and result.temporary:
                result.path.unlink(missing_ok=True)

    @app.get("/api/config/export-bundle")
    def export_bundle(include_uploads: bool = True) -> Any:
        path = build_export_bundle(include_uploads)
        return FileResponse(
            path,
            media_type="application/zip",
            filename=path.name,
        )

    @app.post("/api/config/import-bundle")
    def import_bundle(payload: dict[str, Any]) -> dict[str, Any]:
        content_base64 = str(payload.get("content_base64") or "")
        if "," in content_base64 and content_base64.lstrip().startswith("data:"):
            content_base64 = content_base64.split(",", 1)[1]
        if not content_base64:
            raise HTTPException(status_code=400, detail="content_base64 is required")
        try:
            content = base64.b64decode(content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid base64 bundle content") from exc
        return restore_export_bundle(content)

    @app.post("/api/config/preview-bundle")
    def preview_bundle(payload: dict[str, Any]) -> dict[str, Any]:
        content_base64 = str(payload.get("content_base64") or "")
        if "," in content_base64 and content_base64.lstrip().startswith("data:"):
            content_base64 = content_base64.split(",", 1)[1]
        if not content_base64:
            raise HTTPException(status_code=400, detail="content_base64 is required")
        try:
            content = base64.b64decode(content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid base64 bundle content") from exc
        return preview_export_bundle(content)

    @app.post("/api/open-folder")
    def open_folder(payload: dict[str, Any]) -> dict[str, Any]:
        folder = str(payload.get("folder") or "").strip()
        path = app_folder_path(folder)
        open_folder_in_shell(path)
        return {"status": "ok", "folder": folder, "path": str(path)}

    @app.post("/api/update/check")
    def update_check(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        config_payload = dict(config_payload_from_request(payload))
        config_payload["files"] = []
        runtime_config = load_payload_config(config_payload)
        try:
            return check_for_update(runtime_config.updates).to_dict()
        except UpdateError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/update/download")
    def update_download(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        config_payload = dict(config_payload_from_request(payload))
        config_payload["files"] = []
        runtime_config = load_payload_config(config_payload)
        try:
            return download_update(runtime_config.updates, runtime_config.base_dir).to_dict()
        except UpdateError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/update/apply")
    def update_apply(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        config_payload = dict(config_payload_from_request(payload))
        config_payload["files"] = []
        runtime_config = load_payload_config(config_payload)
        try:
            return apply_update(runtime_config.updates, runtime_config.base_dir, restart=True).to_dict()
        except UpdateError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/jobs")
    def jobs() -> dict[str, Any]:
        engine = SyncEngine(read_runtime_config())
        items = engine.list_jobs()
        running = runner.running_names()
        progress = runner.progress_snapshot()
        for item in items:
            item["running"] = item["name"] in running or "__all__" in running
            item["progress"] = progress.get(item["name"])
        return {"jobs": items}

    @app.get("/api/logs")
    def logs(limit: int = 100) -> dict[str, Any]:
        return {"logs": SyncEngine(read_runtime_config()).recent_logs(limit)}

    @app.post("/api/jobs/{name}/run", status_code=202)
    def run_job(name: str, background_tasks: BackgroundTasks, force: bool = False) -> dict[str, Any]:
        runtime_config = read_runtime_config()
        if name not in {file_config.name for file_config in runtime_config.files}:
            raise HTTPException(status_code=404, detail="Job not found")
        scheduled = runner.schedule_one(background_tasks, name, force)
        return {"status": "accepted" if scheduled else "already_running", "job": name, "force": force}

    @app.post("/api/run-all", status_code=202)
    def run_all(background_tasks: BackgroundTasks, force: bool = False) -> dict[str, Any]:
        scheduled = runner.schedule_all(background_tasks, force)
        return {"status": "accepted" if scheduled else "already_running", "force": force}

    static_dir = config_path.parent.parent / "dist"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

    return app


def _dataframe_preview_rows(dataframe: Any) -> list[list[str]]:
    """Return JSON-safe preview rows with empty cells normalized."""
    rows: list[list[str]] = []
    cleaned = dataframe.fillna("")
    for row in cleaned.itertuples(index=False, name=None):
        rows.append([str(value) if value is not None else "" for value in row])
    return rows


def _suggest_header_row(rows: list[list[str]]) -> int:
    """Suggest a one-based header row from preview rows."""
    best_index = 0
    best_score = -1
    for index, row in enumerate(rows[:10]):
        filled = [cell.strip() for cell in row if str(cell).strip()]
        alpha = sum(1 for cell in filled if any(char.isalpha() for char in cell))
        score = len(filled) + alpha
        if score > best_score:
            best_score = score
            best_index = index
    return best_index + 1


def _resolve_configured_dir(base_dir: Path, value: str) -> Path:
    """Resolve a possibly relative folder from config."""
    path = Path(value or ".")
    if path.is_absolute():
        return path
    return base_dir / path


def _safe_extract_bundle(archive: zipfile.ZipFile, target_dir: Path) -> None:
    """Extract a zip archive without allowing paths outside target_dir."""
    target_dir.mkdir(parents=True, exist_ok=True)
    resolved_target = target_dir.resolve()
    for member in archive.infolist():
        member_path = (target_dir / member.filename).resolve()
        try:
            member_path.relative_to(resolved_target)
        except ValueError as exc:
            raise ValueError("Bundle contains an unsafe path") from exc
    archive.extractall(target_dir)


def _first_existing(*paths: Path) -> Path | None:
    """Return the first existing path from candidates."""
    for path in paths:
        if path.exists():
            return path
    return None
