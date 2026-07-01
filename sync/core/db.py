"""Thao tác PostgreSQL: kết nối, introspection, log, tạo bảng và COPY dữ liệu."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import TYPE_CHECKING, Any, Iterator

from .config import DatabaseConfig
from .schema_compare import ColumnInfo

if TYPE_CHECKING:
    import pandas as pd


VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


class DatabaseError(RuntimeError):
    """Raised when a PostgreSQL operation fails."""


class PostgresClient:
    """Small PostgreSQL adapter for sync operations."""

    def __init__(self, config: DatabaseConfig) -> None:
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
                dbname=self.config.name,
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

    def get_last_success_hash(self, job_name: str, table_name: str) -> str | None:
        """Return the latest successful file hash for a job/table."""
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT file_hash
                    FROM {qualified_name(self.config.schema, "sync_log")}
                    WHERE job_name = %s
                      AND table_name = %s
                      AND status = 'success'
                      AND file_hash IS NOT NULL
                    ORDER BY started_at DESC, id DESC
                    LIMIT 1
                    """,
                    (job_name, table_name),
                )
                row = cursor.fetchone()
                return row[0] if row else None

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
                return [_log_row_to_dict(row) for row in cursor.fetchall()]

    def get_latest_job_logs(self) -> dict[tuple[str, str], dict[str, Any]]:
        """Return the latest log row for each job/table pair."""
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT DISTINCT ON (job_name, table_name)
                           id, job_name, table_name, started_at, finished_at, status,
                           rows_imported, file_hash, file_path, error_message, details
                    FROM {qualified_name(self.config.schema, "sync_log")}
                    ORDER BY job_name, table_name, started_at DESC, id DESC
                    """
                )
                rows = [_log_row_to_dict(row) for row in cursor.fetchall()]
                return {(row["job_name"], row["table_name"]): row for row in rows}

    def get_job_log_history(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Return recent rows used to compute per-job health metrics."""
        bounded_limit = max(1, min(int(limit), 5000))
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
                return [_log_row_to_dict(row) for row in cursor.fetchall()]

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

    def create_table_from_dataframe(
        self,
        schema: str,
        table: str,
        dataframe: "pd.DataFrame",
        unique_columns: list[str] | None = None,
    ) -> None:
        """Create a table using DataFrame dtype inference."""
        if dataframe.empty and not list(dataframe.columns):
            raise DatabaseError("Cannot create a table from a DataFrame with no columns.")

        columns_sql = ", ".join(
            f"{quote_identifier(column)} {_postgres_type_for_series(dataframe[column])}"
            for column in dataframe.columns
        )
        query = f"CREATE TABLE {qualified_name(schema, table)} ({columns_sql})"

        with self.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {quote_identifier(schema)}")
                    cursor.execute(query)
                    if unique_columns:
                        _ensure_unique_index(cursor, schema, table, unique_columns)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def drop_table(self, schema: str, table: str) -> None:
        """Drop a table if it exists."""
        with self.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"DROP TABLE IF EXISTS {qualified_name(schema, table)}")
                connection.commit()
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
                        f"{quote_identifier(column)} {_postgres_type_for_series(dataframe[column])}"
                        for column in dataframe.columns
                    )
                    cursor.execute(f"CREATE TABLE {qualified_name(schema, table)} ({columns_sql})")
                    self._copy_dataframe(cursor, schema, table, dataframe)
                    if unique_columns:
                        _ensure_unique_index(cursor, schema, table, unique_columns)
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

        if update_columns:
            update_sql = "DO UPDATE SET " + ", ".join(
                f"{quote_identifier(column)} = EXCLUDED.{quote_identifier(column)}"
                for column in update_columns
            )
        else:
            update_sql = "DO NOTHING"

        with self.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    _ensure_unique_index(cursor, schema, table, primary_key)
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

        buffer = io.StringIO()
        dataframe.to_csv(
            buffer,
            index=False,
            header=False,
            na_rep="\\N",
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )
        buffer.seek(0)
        column_list = ", ".join(quote_identifier(column) for column in dataframe.columns)
        copy_sql = (
            f"COPY {qualified_name(schema, table)} ({column_list}) "
            "FROM STDIN WITH (FORMAT CSV, HEADER FALSE, NULL '\\N')"
        )
        cursor.copy_expert(copy_sql, buffer)


def validate_upsert_dataframe(dataframe: "pd.DataFrame", primary_key: list[str]) -> None:
    """Validate upsert primary key columns before touching PostgreSQL."""
    missing = [column for column in primary_key if column not in dataframe.columns]
    if missing:
        raise DatabaseError(f"Primary key column(s) missing from source data: {missing}")
    if dataframe.empty:
        return
    null_mask = dataframe[primary_key].isna().any(axis=1)
    if bool(null_mask.any()):
        raise DatabaseError("Primary key column(s) contain null values in source data.")
    duplicate_mask = dataframe.duplicated(subset=primary_key, keep=False)
    if bool(duplicate_mask.any()):
        raise DatabaseError("Primary key values are duplicated in source data.")


def infer_dataframe_schema(dataframe: "pd.DataFrame") -> list[dict[str, Any]]:
    """Return PostgreSQL type preview for a DataFrame."""
    columns: list[dict[str, Any]] = []
    for column in dataframe.columns:
        series = dataframe[column]
        sample = ""
        for value in series.dropna().head(1).tolist():
            sample = str(value)
            break
        columns.append(
            {
                "name": str(column),
                "pandas_type": str(series.dtype),
                "postgres_type": _postgres_type_for_series(series),
                "nullable": bool(series.isna().any()),
                "sample": sample,
            }
        )
    return columns


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


def _ensure_unique_index(cursor: Any, schema: str, table: str, columns: list[str]) -> None:
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


def _postgres_type_for_series(series: "pd.Series") -> str:
    """Map a pandas Series dtype to a PostgreSQL type."""
    try:
        from pandas.api import types as pd_types
    except ImportError as exc:
        raise DatabaseError("pandas is required for dtype mapping.") from exc

    if pd_types.is_bool_dtype(series):
        return "BOOLEAN"
    if pd_types.is_integer_dtype(series):
        return "BIGINT"
    if pd_types.is_float_dtype(series):
        return "DOUBLE PRECISION"
    if pd_types.is_datetime64_any_dtype(series):
        return "TIMESTAMP"
    return "TEXT"


def _log_row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    """Convert a sync_log SQL row to a dictionary."""
    keys = [
        "id",
        "job_name",
        "table_name",
        "started_at",
        "finished_at",
        "status",
        "rows_imported",
        "file_hash",
        "file_path",
        "error_message",
        "details",
    ]
    return dict(zip(keys, row, strict=True))
