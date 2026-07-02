"""Local SQLite state store for sync history and hash tracking."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


CURRENT_SCHEMA_VERSION = 1


class StateStoreError(RuntimeError):
    """Raised when the local sync state store cannot be accessed."""


class SyncStateStore:
    """SQLite-backed canonical sync state for monitor and hash skip."""

    def __init__(self, base_dir: Path, log_dir: str = "./logs") -> None:
        self.path = _state_db_path(base_dir, log_dir)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Open a SQLite connection with row dictionaries enabled."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def ensure(self) -> None:
        """Create or migrate local sync state tables if needed."""
        with self.connection() as connection:
            _migrate(connection)

    def insert_sync_log(
        self,
        *,
        job_name: str,
        connection_id: str,
        connection_name: str,
        engine: str,
        target_schema: str,
        target_table: str,
        table_name: str,
        started_at: datetime,
        finished_at: datetime,
        status: str,
        rows_imported: int,
        file_hash: str | None,
        file_path: str | None,
        error_message: str | None,
        details: dict[str, Any] | None,
    ) -> None:
        """Insert one canonical local sync log row."""
        self.ensure()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO sync_log (
                    job_name, connection_id, connection_name, engine,
                    target_schema, target_table, table_name, started_at, finished_at,
                    status, rows_imported, file_hash, file_path, error_message, details
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_name,
                    connection_id,
                    connection_name,
                    engine,
                    target_schema,
                    target_table,
                    table_name,
                    started_at.isoformat(),
                    finished_at.isoformat(),
                    status,
                    rows_imported,
                    file_hash,
                    file_path,
                    error_message,
                    json.dumps(details or {}, ensure_ascii=False),
                ),
            )

    def get_last_success_hash(
        self,
        *,
        job_name: str,
        connection_id: str,
        target_schema: str,
        target_table: str,
    ) -> str | None:
        """Return latest successful hash for a job and concrete target."""
        self.ensure()
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT file_hash
                FROM sync_log
                WHERE job_name = ?
                  AND connection_id = ?
                  AND target_schema = ?
                  AND target_table = ?
                  AND status = 'success'
                  AND file_hash IS NOT NULL
                ORDER BY started_at DESC, id DESC
                LIMIT 1
                """,
                (job_name, connection_id, target_schema, target_table),
            ).fetchone()
            return str(row["file_hash"]) if row else None

    def get_recent_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return recent local sync logs."""
        self.ensure()
        bounded_limit = max(1, min(int(limit), 500))
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM sync_log
                ORDER BY started_at DESC, id DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
            return [_row_to_dict(row) for row in rows]

    def get_latest_job_logs(self) -> dict[tuple[str, str, str, str], dict[str, Any]]:
        """Return latest local log for each job/connection/schema/table target."""
        self.ensure()
        latest: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for row in self.get_recent_logs(5000):
            key = (row["job_name"], row["connection_id"], row["target_schema"], row["target_table"])
            latest.setdefault(key, row)
        return latest

    def get_job_log_history(self, limit: int = 5000) -> list[dict[str, Any]]:
        """Return recent local history for health metrics."""
        return self.get_recent_logs(limit)

    def cleanup_sync_log(self, retention_days: int) -> int:
        """Delete old local sync logs and return deleted row count."""
        self.ensure()
        cutoff = datetime.now().timestamp() - max(1, retention_days) * 86400
        deleted = 0
        with self.connection() as connection:
            rows = connection.execute("SELECT id, started_at FROM sync_log").fetchall()
            for row in rows:
                try:
                    started = datetime.fromisoformat(str(row["started_at"])).timestamp()
                except ValueError:
                    started = 0
                if started < cutoff:
                    connection.execute("DELETE FROM sync_log WHERE id = ?", (row["id"],))
                    deleted += 1
        return deleted


def _state_db_path(base_dir: Path, log_dir: str) -> Path:
    """Return the SQLite state database path under the configured log directory."""
    path = Path(log_dir or "./logs")
    if not path.is_absolute():
        path = base_dir / path
    return path / "sync_state.sqlite"


def _migrate(connection: sqlite3.Connection) -> None:
    """Apply idempotent SQLite schema migrations."""
    current = int(connection.execute("PRAGMA user_version").fetchone()[0] or 0)
    if current < 1:
        _create_schema_v1(connection)
        _set_schema_version(connection, 1)
    if current > CURRENT_SCHEMA_VERSION:
        raise StateStoreError(
            f"SQLite state schema version {current} is newer than this app supports ({CURRENT_SCHEMA_VERSION})."
        )


def _create_schema_v1(connection: sqlite3.Connection) -> None:
    """Create the first local sync state schema."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_name TEXT NOT NULL,
            connection_id TEXT NOT NULL,
            connection_name TEXT NOT NULL,
            engine TEXT NOT NULL,
            target_schema TEXT NOT NULL,
            target_table TEXT NOT NULL,
            table_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            rows_imported INTEGER DEFAULT 0,
            file_hash TEXT,
            file_path TEXT,
            error_message TEXT,
            details TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sync_state_job_target
        ON sync_log (job_name, connection_id, target_schema, target_table, started_at DESC, id DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sync_state_started
        ON sync_log (started_at DESC, id DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sync_state_status
        ON sync_log (status)
        """
    )


def _set_schema_version(connection: sqlite3.Connection, version: int) -> None:
    """Persist SQLite state schema version in PRAGMA and metadata table."""
    connection.execute("CREATE TABLE IF NOT EXISTS sync_state_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute("PRAGMA user_version = %d" % version)
    connection.execute(
        """
        INSERT INTO sync_state_meta (key, value)
        VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(version),),
    )


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert one SQLite row to the API log dictionary."""
    result = dict(row)
    details = result.get("details")
    if isinstance(details, str) and details:
        try:
            result["details"] = json.loads(details)
        except json.JSONDecodeError:
            result["details"] = {"raw": details}
    else:
        result["details"] = {}
    return result
