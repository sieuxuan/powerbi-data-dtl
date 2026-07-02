from __future__ import annotations

import unittest
from pathlib import Path

from core.config import (
    ApiConfig,
    AppConfig,
    DatabaseConfig,
    DatabaseConnectionConfig,
    DownloadsConfig,
    LoggingConfig,
    NotificationConfig,
    RetryConfig,
    ScheduleConfig,
    SourceConfig,
    SyncFileConfig,
    TargetConfig,
    UpdateConfig,
)
from core.scheduler import SyncRuntime


class SchedulerTests(unittest.TestCase):
    def test_default_cron_is_used_when_job_has_no_schedule(self) -> None:
        runtime = SyncRuntime(_config(default_cron="5 6 * * *"))
        runtime._start_scheduler()
        try:
            status = runtime._scheduler_status()
        finally:
            runtime.stop()

        self.assertEqual(status["scheduled_jobs"], 1)
        self.assertEqual(status["next_runs"][0]["id"], "sync:Scheduled job:1")

    def test_on_startup_submits_enabled_jobs_once(self) -> None:
        runtime = SyncRuntime(_config(on_startup=True))
        submitted: list[str] = []
        runtime._submit_job = submitted.append  # type: ignore[method-assign]

        runtime.start()
        try:
            self.assertEqual(submitted, ["Scheduled job"])
        finally:
            runtime.stop()


def _config(*, default_cron: str = "0 6 * * *", on_startup: bool = False) -> AppConfig:
    connection = DatabaseConnectionConfig(
        id="default",
        name="Default",
        engine="postgresql",
        host="localhost",
        port=5432,
        database="dummy",
        user="dummy",
        password="",
        schema="public",
    )
    return AppConfig(
        database=DatabaseConfig(host="localhost", port=5432, name="dummy", user="dummy", password="", schema="public"),
        database_connections=[connection],
        schedule=ScheduleConfig(default_cron=default_cron, timezone="Asia/Ho_Chi_Minh", on_startup=on_startup),
        files=[
            SyncFileConfig(
                name="Scheduled job",
                source=SourceConfig(type="local", path="dummy.csv"),
                target=TargetConfig(table="dummy_table", schema="public", connection_id="default"),
                enabled=True,
            )
        ],
        notifications=NotificationConfig(),
        logging=LoggingConfig(log_to_db=False),
        downloads=DownloadsConfig(),
        updates=UpdateConfig(enabled=False),
        api=ApiConfig(enabled=False),
        retry=RetryConfig(),
        config_path=Path("sync/config.yaml").resolve(),
        base_dir=Path("sync").resolve(),
    )


if __name__ == "__main__":
    unittest.main()
