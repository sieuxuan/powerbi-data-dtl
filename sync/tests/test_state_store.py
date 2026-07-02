from __future__ import annotations

import tempfile
import unittest
import sqlite3
from datetime import datetime
from pathlib import Path

from core.state_store import CURRENT_SCHEMA_VERSION, SyncStateStore


class SyncStateStoreTests(unittest.TestCase):
    def test_writes_logs_and_reads_latest_success_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SyncStateStore(Path(temp_dir), "./logs")
            started = datetime.now()

            store.insert_sync_log(
                job_name="sales",
                connection_id="warehouse_sqlserver",
                connection_name="Warehouse",
                engine="sqlserver",
                target_schema="dbo",
                target_table="sales",
                table_name="dbo.sales",
                started_at=started,
                finished_at=started,
                status="success",
                rows_imported=10,
                file_hash="abc123",
                file_path="sales.csv",
                error_message=None,
                details={"source": "unit"},
            )

            self.assertEqual(
                store.get_last_success_hash(
                    job_name="sales",
                    connection_id="warehouse_sqlserver",
                    target_schema="dbo",
                    target_table="sales",
                ),
                "abc123",
            )
            logs = store.get_recent_logs(10)
            self.assertEqual(logs[0]["connection_id"], "warehouse_sqlserver")
            self.assertEqual(logs[0]["engine"], "sqlserver")
            self.assertEqual(logs[0]["details"], {"source": "unit"})

    def test_ensure_writes_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SyncStateStore(Path(temp_dir), "./logs")
            store.ensure()

            connection = sqlite3.connect(store.path)
            try:
                user_version = connection.execute("PRAGMA user_version").fetchone()[0]
                meta_version = connection.execute(
                    "SELECT value FROM sync_state_meta WHERE key = 'schema_version'"
                ).fetchone()[0]
            finally:
                connection.close()

            self.assertEqual(user_version, CURRENT_SCHEMA_VERSION)
            self.assertEqual(meta_version, str(CURRENT_SCHEMA_VERSION))


if __name__ == "__main__":
    unittest.main()
