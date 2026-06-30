"""Scheduler APScheduler và runtime foreground/API cho sync service."""

from __future__ import annotations

import logging
import signal
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .config import AppConfig, enabled_files, load_config
from .sync_engine import SyncEngine
from .updater import check_and_download_if_enabled


LOGGER = logging.getLogger(__name__)


class SyncRuntime:
    """Owns the scheduler, optional API server, and graceful shutdown."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.stop_event = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=max(2, len(enabled_files(config)) or 1))
        self.scheduler: Any | None = None
        self.api_server: Any | None = None
        self.api_thread: threading.Thread | None = None
        self.config_mtime = self._config_mtime()

    def start(self) -> None:
        """Start scheduler and API server."""
        self._start_scheduler()
        if self.config.api.enabled:
            self._start_api()
        self._check_updates_on_startup()

    def stop(self) -> None:
        """Stop scheduler and API server."""
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
        if self.api_server:
            self.api_server.should_exit = True
        if self.api_thread and self.api_thread.is_alive():
            self.api_thread.join(timeout=10)
        self.executor.shutdown(wait=False, cancel_futures=True)

    def run_forever(self) -> None:
        """Block until SIGINT/SIGTERM requests shutdown."""
        self.start()

        def request_stop(signum: int, _frame: object) -> None:
            LOGGER.info("Received signal %s. Stopping sync runtime.", signum)
            self.stop_event.set()

        signal.signal(signal.SIGINT, request_stop)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, request_stop)

        try:
            LOGGER.info("Sync runtime started. Press Ctrl+C to stop.")
            while not self.stop_event.wait(1):
                self._reload_config_if_changed()
        finally:
            self.stop()

    def _start_scheduler(self) -> None:
        """Configure APScheduler jobs."""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
        except ImportError as exc:
            raise RuntimeError("APScheduler is required. Install dependencies with: pip install -r requirements.txt") from exc

        self.scheduler = BackgroundScheduler(
            timezone=self.config.schedule.timezone,
            job_defaults={"coalesce": True, "max_instances": 1},
        )
        self._schedule_jobs()
        self.scheduler.start()
        LOGGER.info("Scheduler started; jobs run only by cron schedule or manual trigger.")

    def _schedule_jobs(self) -> None:
        """Register enabled file jobs on the current scheduler."""
        try:
            from apscheduler.triggers.cron import CronTrigger
        except ImportError as exc:
            raise RuntimeError("APScheduler is required. Install dependencies with: pip install -r requirements.txt") from exc

        if self.scheduler is None:
            return
        self.scheduler.remove_all_jobs()
        for file_config in enabled_files(self.config):
            crons = file_config.crons or ([file_config.cron] if file_config.cron else [])
            if not crons:
                LOGGER.info("Job %s has no cron schedule; it can still run manually.", file_config.name)
                continue
            for index, cron in enumerate(crons, start=1):
                trigger = CronTrigger.from_crontab(cron, timezone=self.config.schedule.timezone)
                self.scheduler.add_job(
                    self._submit_job,
                    trigger=trigger,
                    id=f"sync:{file_config.name}:{index}",
                    name=file_config.name,
                    args=[file_config.name],
                    replace_existing=True,
                )
                LOGGER.info("Scheduled %s with cron '%s'.", file_config.name, cron)

    def _config_mtime(self) -> float | None:
        """Return current config mtime for lightweight reload detection."""
        try:
            return self.config.config_path.stat().st_mtime
        except OSError:
            return None

    def _reload_config_if_changed(self) -> None:
        """Reload scheduler jobs when config.yaml changes on disk."""
        current_mtime = self._config_mtime()
        if current_mtime is None or current_mtime == self.config_mtime:
            return
        try:
            next_config = load_config(self.config.config_path)
        except Exception:
            LOGGER.exception("Config changed but could not be reloaded; keeping current scheduler jobs.")
            return
        self.config = next_config
        self.config_mtime = current_mtime
        self._schedule_jobs()
        LOGGER.info("Reloaded sync config and rescheduled jobs from %s.", self.config.config_path)

    def _submit_job(self, name: str) -> None:
        """Submit one scheduler job to the executor."""
        LOGGER.info("Scheduler triggered job: %s", name)
        self._reload_config_if_changed()
        config = self.config
        self.executor.submit(lambda: SyncEngine(config).run_by_name(name))

    def _start_api(self) -> None:
        """Start the local FastAPI server in a background thread."""
        try:
            import uvicorn

            from .api import create_app
        except ImportError as exc:
            raise RuntimeError("FastAPI and uvicorn are required. Install dependencies with requirements.txt") from exc

        app = create_app(self.config, runtime_status=self._scheduler_status)
        uvicorn_config = uvicorn.Config(
            app,
            host=self.config.api.host,
            port=self.config.api.port,
            log_level="info",
        )
        self.api_server = uvicorn.Server(uvicorn_config)
        self.api_thread = threading.Thread(target=self.api_server.run, name="sync-api", daemon=True)
        self.api_thread.start()
        LOGGER.info("Sync API listening on http://%s:%s", self.config.api.host, self.config.api.port)

    def _scheduler_status(self) -> dict[str, Any]:
        """Return scheduler status for the local API health endpoint."""
        if self.scheduler is None:
            return {"enabled": False, "running": False, "scheduled_jobs": 0, "next_runs": []}
        next_runs = []
        for job in self.scheduler.get_jobs():
            next_runs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                }
            )
        return {
            "enabled": True,
            "running": bool(getattr(self.scheduler, "running", False)),
            "scheduled_jobs": len(next_runs),
            "next_runs": next_runs,
        }

    def _check_updates_on_startup(self) -> None:
        """Run a best-effort GitHub update check in the background."""
        if not self.config.updates.enabled or not self.config.updates.check_on_startup:
            return

        def task() -> None:
            try:
                info = check_and_download_if_enabled(self.config.updates, self.config.base_dir)
                LOGGER.info("Update check: %s", info.message)
            except Exception:
                LOGGER.exception("Update check failed.")

        self.executor.submit(task)


def run_foreground(config: AppConfig) -> None:
    """Run scheduler/API in the foreground until interrupted."""
    SyncRuntime(config).run_forever()
