from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from core.config import (
    ApiConfig,
    AppConfig,
    DatabaseConfig,
    DatabaseConnectionConfig,
    DownloadsConfig,
    LoggingConfig,
    NotificationConfig,
    RetryConfig,
    RetryPolicy,
    ScheduleConfig,
    SourceConfig,
    SyncFileConfig,
    TargetConfig,
    UpdateConfig,
)
from core.file_reader import calculate_md5
from core.state_store import SyncStateStore
from core.sync_engine import SyncEngine


class FakeDb:
    def __init__(self, expected_hash: str) -> None:
        self.expected_hash = expected_hash
        self.logs: list[dict[str, object]] = []
        self.ensured = 0

    def ensure_sync_log_table(self) -> None:
        self.ensured += 1
        return None

    def get_last_success_hash(self, _job_name: str, _table_name: str) -> str:
        return self.expected_hash

    def insert_sync_log(self, **kwargs: object) -> None:
        self.logs.append(kwargs)


class FakeImportDb(FakeDb):
    def __init__(self) -> None:
        super().__init__("")

    def table_exists(self, _schema: str, _table: str) -> bool:
        return False

    def replace_table(self, _schema: str, _table: str, dataframe: object, _unique_columns: object = None) -> int:
        return len(dataframe)


class SyncHashSkipTests(unittest.TestCase):
    def test_unchanged_file_skips_before_reading(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            source = base_dir / "sample.csv"
            source.write_text("id,name\n1,A\n", encoding="utf-8")
            file_hash = calculate_md5(source)
            fake_db = FakeDb(file_hash)
            state = SyncStateStore(base_dir, "./logs")
            state.insert_sync_log(
                job_name="sample",
                connection_id="default",
                connection_name="Default PostgreSQL",
                engine="postgresql",
                target_schema="public",
                target_table="sample",
                table_name="public.sample",
                started_at=datetime.now(),
                finished_at=datetime.now(),
                status="success",
                rows_imported=1,
                file_hash=file_hash,
                file_path=str(source),
                error_message=None,
                details={},
            )
            config = AppConfig(
                database=DatabaseConfig(host="localhost", port=5432, name="db", user="postgres", password="", schema="public"),
                database_connections=[
                    DatabaseConnectionConfig(
                        id="default",
                        name="Default PostgreSQL",
                        engine="postgresql",
                        host="localhost",
                        port=5432,
                        database="db",
                        user="postgres",
                        password="",
                        schema="public",
                    )
                ],
                schedule=ScheduleConfig(),
                files=[
                    SyncFileConfig(
                        name="sample",
                        source=SourceConfig(type="local", path=str(source)),
                        target=TargetConfig(table="sample"),
                    )
                ],
                notifications=NotificationConfig(),
                logging=LoggingConfig(),
                downloads=DownloadsConfig(),
                updates=UpdateConfig(),
                api=ApiConfig(enabled=False),
                retry=RetryConfig(
                    db=RetryPolicy(attempts=1, delay_seconds=0),
                    file=RetryPolicy(attempts=1, delay_seconds=0),
                    onedrive=RetryPolicy(attempts=1, delay_seconds=0),
                ),
                config_path=base_dir / "config.yaml",
                base_dir=base_dir,
            )

            with patch("core.sync_engine.create_sql_target_client", return_value=fake_db):
                engine = SyncEngine(config)
                result = engine.run_by_name("sample")

            self.assertEqual(result.status, "skipped")
            self.assertEqual(result.details["reason"], "unchanged")
            self.assertEqual(engine.recent_logs(1)[0]["status"], "skipped")

    def test_log_to_db_false_does_not_write_sync_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            source = base_dir / "sample.csv"
            source.write_text("id,name\n1,A\n", encoding="utf-8")
            fake_db = FakeImportDb()
            config = AppConfig(
                database=DatabaseConfig(host="localhost", port=5432, name="db", user="postgres", password="", schema="public"),
                database_connections=[
                    DatabaseConnectionConfig(
                        id="default",
                        name="Default PostgreSQL",
                        engine="postgresql",
                        host="localhost",
                        port=5432,
                        database="db",
                        user="postgres",
                        password="",
                        schema="public",
                    )
                ],
                schedule=ScheduleConfig(),
                files=[
                    SyncFileConfig(
                        name="sample",
                        source=SourceConfig(type="local", path=str(source)),
                        target=TargetConfig(table="sample"),
                    )
                ],
                notifications=NotificationConfig(),
                logging=LoggingConfig(log_to_db=False),
                downloads=DownloadsConfig(),
                updates=UpdateConfig(),
                api=ApiConfig(enabled=False),
                retry=RetryConfig(
                    db=RetryPolicy(attempts=1, delay_seconds=0),
                    file=RetryPolicy(attempts=1, delay_seconds=0),
                    onedrive=RetryPolicy(attempts=1, delay_seconds=0),
                ),
                config_path=base_dir / "config.yaml",
                base_dir=base_dir,
            )

            with patch("core.sync_engine.create_sql_target_client", return_value=fake_db):
                engine = SyncEngine(config)
                result = engine.run_by_name("sample")

            self.assertEqual(result.status, "success")
            self.assertEqual(fake_db.logs, [])
            self.assertEqual(fake_db.ensured, 0)
            self.assertEqual(engine.recent_logs(1)[0]["status"], "success")


if __name__ == "__main__":
    unittest.main()
