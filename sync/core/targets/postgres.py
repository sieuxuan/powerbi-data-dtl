"""PostgreSQL target adapter."""

from __future__ import annotations

import csv
import hashlib
import io
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import TYPE_CHECKING, Any, Iterator

from ..config import DatabaseConfig, DatabaseConnectionConfig
from ..schema_compare import ColumnInfo
from .common import (
    DatabaseError,
    VALID_IDENTIFIER,
    connection_database,
    log_row_to_dict,
    postgres_type_for_series,
    validate_upsert_dataframe,
)

if TYPE_CHECKING:
    import pandas as pd


class PostgresClient:
    """PostgreSQL adapter for sync operations."""

    def __init__(self, config: DatabaseConfig | DatabaseConnectionConfig) -> None:
        self.config = config
        self._psycopg2: Any | None = None
        self._pool: Any | None = None

    @contextmanager
    def connection(self) -> Iterator[Any]:
        """Borrow a PostgreSQL connection from a persistent pool."""
        if self._psycopg2 is None:
            try:
                import psycopg2
                from psycopg2 import pool
            except ImportError as exc:
                raise DatabaseError(
                    "psycopg2-binary is required. Install dependencies with: pip install -r requirements.txt"
                ) from exc
            self._psycopg2 = psycopg2
            self._pool = pool.SimpleConnectionPool(
                1,
                5,
                host=self.config.host,
                port=self.config.port,
                dbname=connection_database(self.config),
                user=self.config.user,
                password=self.config.password,
                connect_timeout=5,
            )

        connection = self._pool.getconn()
        try:
            yield connection
        finally:
            self._pool.putconn(connection)

    def close(self) -> None:
        """Close all pooled database connections."""
        if self._pool is not None:
            self._pool.closeall()
            self._pool = None

    def test_connection(self) -> None:
        """Execute a simple health check query."""
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()

    def test_write_permission(self, schema: str) -> None:
        """Create, write to, and drop a throwaway table in the target schema."""
        test_table = f"_sync_write_test_{uuid.uuid4().hex[:10]}"
        with self.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {quote_identifier(schema)}")
                    cursor.execute(f"CREATE TABLE {qualified_name(schema, test_table)} (id INTEGER)")
                    cursor.execute(f"INSERT INTO {qualified_name(schema, test_table)} (id) VALUES (1)")
                    cursor.execute(f"DROP TABLE {qualified_name(schema, test_table)}")
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def ensure_sync_log_table(self) -> None:
        """Create the sync_log table if it does not exist."""
        with self.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {quote_identifier(self.config.schema)}")
                    cursor.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {qualified_name(self.config.schema, "sync_log")} (
                            id SERIAL PRIMARY KEY,
                            job_name VARCHAR(255) NOT NULL,
                            table_name VARCHAR(255) NOT NULL,
                            started_at TIMESTAMP NOT NULL DEFAULT NOW(),
                            finished_at TIMESTAMP,
                            status VARCHAR(20) NOT NULL,
                            rows_imported INTEGER DEFAULT 0,
                            file_hash VARCHAR(64),
                            file_path TEXT,
                            error_message TEXT,
                            details JSONB
                        )
                        """
                    )
                    cursor.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS {quote_identifier("idx_sync_log_job_started")}
                        ON {qualified_name(self.config.schema, "sync_log")} (job_name, started_at DESC)
                        """
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def insert_sync_log(
        self,
        *,
        job_name: str,
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
        """Insert one sync result row into sync_log."""
        from psycopg2.extras import Json

        with self.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"""
                        INSERT INTO {qualified_name(self.config.schema, "sync_log")} (
                            job_name, table_name, started_at, finished_at, status,
                            rows_imported, file_hash, file_path, error_message, details
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            job_name,
                            table_name,
                            started_at,
                            finished_at,
                            status,
                            rows_imported,
                            file_hash,
                            file_path,
                            error_message,
                            Json(details or {}),
                        ),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def get_recent_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return recent sync_log rows."""
        bounded_limit = max(1, min(int(limit), 500))
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT id, job_name, table_name, started_at, finished_at, status,
                           rows_imported, file_hash, file_path, error_message, details
                    FROM {qualified_name(self.config.schema, "sync_log")}
                    ORDER BY started_at DESC, id DESC
                    LIMIT %s
                    """,
                    (bounded_limit,),
                )
                return [log_row_to_dict(row) for row in cursor.fetchall()]

    def cleanup_sync_log(self, retention_days: int) -> int:
        """Delete old sync_log rows and return the number of deleted rows."""
        with self.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"""
                        DELETE FROM {qualified_name(self.config.schema, "sync_log")}
                        WHERE started_at < NOW() - (%s * INTERVAL '1 day')
                        """,
                        (retention_days,),
                    )
                    deleted = cursor.rowcount
                connection.commit()
                return int(deleted or 0)
            except Exception:
                connection.rollback()
                raise

    def table_exists(self, schema: str, table: str) -> bool:
        """Return whether a table exists."""
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = %s AND table_name = %s
                    )
                    """,
                    (schema, table),
                )
                return bool(cursor.fetchone()[0])

    def get_columns(self, schema: str, table: str) -> list[ColumnInfo]:
        """Return column metadata for a table ordered by ordinal position."""
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (schema, table),
                )
                return [
                    ColumnInfo(name=row[0], data_type=row[1], is_nullable=row[2] == "YES")
                    for row in cursor.fetchall()
                ]

    def replace_table(
        self,
        schema: str,
        table: str,
        dataframe: "pd.DataFrame",
        unique_columns: list[str] | None = None,
    ) -> int:
        """Drop, recreate, and bulk insert DataFrame rows in one transaction."""
        with self.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {quote_identifier(schema)}")
                    cursor.execute(f"DROP TABLE IF EXISTS {qualified_name(schema, table)}")
                    columns_sql = ", ".join(
                        f"{quote_identifier(column)} {postgres_type_for_series(dataframe[column])}"
                        for column in dataframe.columns
                    )
                    cursor.execute(f"CREATE TABLE {qualified_name(schema, table)} ({columns_sql})")
                    self._copy_dataframe(cursor, schema, table, dataframe)
                    if unique_columns:
                        ensure_unique_index(cursor, schema, table, unique_columns)
                connection.commit()
                return len(dataframe)
            except Exception:
                connection.rollback()
                raise

    def truncate_insert(self, schema: str, table: str, dataframe: "pd.DataFrame") -> int:
        """Truncate a table and bulk insert DataFrame rows in one transaction."""
        with self.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"TRUNCATE TABLE {qualified_name(schema, table)}")
                    self._copy_dataframe(cursor, schema, table, dataframe)
                connection.commit()
                return len(dataframe)
            except Exception:
                connection.rollback()
                raise

    def append_insert(self, schema: str, table: str, dataframe: "pd.DataFrame") -> int:
        """Bulk append DataFrame rows."""
        with self.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    self._copy_dataframe(cursor, schema, table, dataframe)
                connection.commit()
                return len(dataframe)
            except Exception:
                connection.rollback()
                raise

    def upsert_insert(
        self,
        schema: str,
        table: str,
        dataframe: "pd.DataFrame",
        primary_key: list[str],
    ) -> int:
        """Bulk upsert DataFrame rows using a temporary table."""
        validate_upsert_dataframe(dataframe, primary_key)
        if dataframe.empty:
            return 0

        temp_table = f"_sync_{table[:32]}_{uuid.uuid4().hex[:8]}"
        columns = list(dataframe.columns)
        column_list = ", ".join(quote_identifier(column) for column in columns)
        conflict_list = ", ".join(quote_identifier(column) for column in primary_key)
        update_columns = [column for column in columns if column not in primary_key]
        update_sql = "DO NOTHING"
        if update_columns:
            update_sql = "DO UPDATE SET " + ", ".join(
                f"{quote_identifier(column)} = EXCLUDED.{quote_identifier(column)}"
                for column in update_columns
            )

        with self.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    ensure_unique_index(cursor, schema, table, primary_key)
                    cursor.execute(
                        f"""
                        CREATE TEMP TABLE {quote_identifier(temp_table)}
                        (LIKE {qualified_name(schema, table)} INCLUDING DEFAULTS)
                        ON COMMIT DROP
                        """
                    )
                    self._copy_dataframe(cursor, "pg_temp", temp_table, dataframe)
                    cursor.execute(
                        f"""
                        INSERT INTO {qualified_name(schema, table)} ({column_list})
                        SELECT {column_list}
                        FROM {qualified_name("pg_temp", temp_table)}
                        ON CONFLICT ({conflict_list}) {update_sql}
                        """
                    )
                connection.commit()
                return len(dataframe)
            except Exception:
                connection.rollback()
                raise

    def _copy_dataframe(self, cursor: Any, schema: str, table: str, dataframe: "pd.DataFrame") -> None:
        """Copy DataFrame rows into PostgreSQL using COPY FROM STDIN."""
        if dataframe.empty:
            return

        null_marker = f"__SYNC_NULL_{uuid.uuid4().hex}__"
        buffer = io.StringIO()
        dataframe.to_csv(
            buffer,
            index=False,
            header=False,
            na_rep=null_marker,
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )
        buffer.seek(0)
        column_list = ", ".join(quote_identifier(column) for column in dataframe.columns)
        copy_sql = (
            f"COPY {qualified_name(schema, table)} ({column_list}) "
            f"FROM STDIN WITH (FORMAT CSV, HEADER FALSE, NULL '{null_marker}')"
        )
        cursor.copy_expert(copy_sql, buffer)


def quote_identifier(identifier: str) -> str:
    """Quote and validate a PostgreSQL identifier."""
    if not VALID_IDENTIFIER.match(identifier):
        raise DatabaseError(
            f"Invalid PostgreSQL identifier '{identifier}'. Use letters, numbers and underscores; do not start with a number."
        )
    return f'"{identifier}"'


def qualified_name(schema: str, table: str) -> str:
    """Return a quoted schema-qualified table name."""
    return f"{quote_identifier(schema)}.{quote_identifier(table)}"


def ensure_unique_index(cursor: Any, schema: str, table: str, columns: list[str]) -> None:
    """Create a deterministic unique index for upsert conflict keys."""
    for column in columns:
        quote_identifier(column)
    suffix = hashlib.md5("|".join(columns).encode("utf-8")).hexdigest()[:8]
    index_name = f"{table[:48]}_{suffix}_uidx"
    column_list = ", ".join(quote_identifier(column) for column in columns)
    cursor.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {quote_identifier(index_name)}
        ON {qualified_name(schema, table)} ({column_list})
        """
    )
