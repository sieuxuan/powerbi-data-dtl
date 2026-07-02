"""Microsoft SQL Server target adapter."""

from __future__ import annotations

import hashlib
import uuid
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Iterator

from ..config import DatabaseConnectionConfig
from ..schema_compare import ColumnInfo
from .common import (
    DatabaseError,
    VALID_IDENTIFIER,
    sqlserver_type_for_series,
    validate_upsert_dataframe,
)

if TYPE_CHECKING:
    import pandas as pd


class SqlServerClient:
    """Microsoft SQL Server adapter for sync operations."""

    def __init__(self, config: DatabaseConnectionConfig) -> None:
        self.config = config
        self._pyodbc: Any | None = None

    @contextmanager
    def connection(self) -> Iterator[Any]:
        """Open a SQL Server connection."""
        if self._pyodbc is None:
            try:
                import pyodbc
            except ImportError as exc:
                raise DatabaseError(
                    "pyodbc is required for SQL Server targets. Install it and Microsoft ODBC Driver 18 for SQL Server."
                ) from exc
            self._pyodbc = pyodbc
        connection = self._pyodbc.connect(sqlserver_connection_string(self.config), timeout=5)
        try:
            yield connection
        finally:
            connection.close()

    def close(self) -> None:
        """Close pooled resources; SQL Server connections are not pooled."""
        return None

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
                    cursor.execute(sqlserver_create_schema_sql(schema))
                    cursor.execute(f"CREATE TABLE {sqlserver_qualified_name(schema, test_table)} ([id] INT)")
                    cursor.execute(f"INSERT INTO {sqlserver_qualified_name(schema, test_table)} ([id]) VALUES (1)")
                    cursor.execute(f"DROP TABLE {sqlserver_qualified_name(schema, test_table)}")
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def table_exists(self, schema: str, table: str) -> bool:
        """Return whether a table exists."""
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 1
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
                    """,
                    (schema, table),
                )
                return cursor.fetchone() is not None

    def get_columns(self, schema: str, table: str) -> list[ColumnInfo]:
        """Return column metadata for a table ordered by ordinal position."""
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
                    ORDER BY ORDINAL_POSITION
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
                    cursor.execute(sqlserver_create_schema_sql(schema))
                    cursor.execute(sqlserver_drop_table_sql(schema, table))
                    columns_sql = ", ".join(
                        f"{quote_sqlserver_identifier(column)} {sqlserver_type_for_series(dataframe[column])}"
                        for column in dataframe.columns
                    )
                    cursor.execute(f"CREATE TABLE {sqlserver_qualified_name(schema, table)} ({columns_sql})")
                    self._bulk_insert(cursor, schema, table, dataframe)
                    if unique_columns:
                        ensure_sqlserver_unique_index(cursor, schema, table, unique_columns)
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
                    cursor.execute(f"TRUNCATE TABLE {sqlserver_qualified_name(schema, table)}")
                    self._bulk_insert(cursor, schema, table, dataframe)
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
                    self._bulk_insert(cursor, schema, table, dataframe)
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
        """Bulk upsert rows through a staging table without using MERGE."""
        validate_upsert_dataframe(dataframe, primary_key)
        if dataframe.empty:
            return 0

        staging = f"_sync_{table[:32]}_{uuid.uuid4().hex[:8]}"
        columns = list(dataframe.columns)
        non_key_columns = [column for column in columns if column not in primary_key]
        target = sqlserver_qualified_name(schema, table)
        staging_name = sqlserver_qualified_name(schema, staging)
        column_list = ", ".join(quote_sqlserver_identifier(column) for column in columns)
        join_condition = " AND ".join(
            f"target.{quote_sqlserver_identifier(column)} = source.{quote_sqlserver_identifier(column)}"
            for column in primary_key
        )

        with self.connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(sqlserver_drop_table_sql(schema, staging))
                    cursor.execute(f"SELECT TOP 0 {column_list} INTO {staging_name} FROM {target}")
                    self._bulk_insert(cursor, schema, staging, dataframe)
                    if non_key_columns:
                        assignments = ", ".join(
                            f"target.{quote_sqlserver_identifier(column)} = source.{quote_sqlserver_identifier(column)}"
                            for column in non_key_columns
                        )
                        cursor.execute(
                            f"""
                            UPDATE target
                            SET {assignments}
                            FROM {target} AS target
                            INNER JOIN {staging_name} AS source ON {join_condition}
                            """
                        )
                    cursor.execute(
                        f"""
                        INSERT INTO {target} ({column_list})
                        SELECT {column_list}
                        FROM {staging_name} AS source
                        WHERE NOT EXISTS (
                            SELECT 1 FROM {target} AS target WHERE {join_condition}
                        )
                        """
                    )
                    cursor.execute(sqlserver_drop_table_sql(schema, staging))
                connection.commit()
                return len(dataframe)
            except Exception:
                connection.rollback()
                raise

    def _bulk_insert(self, cursor: Any, schema: str, table: str, dataframe: "pd.DataFrame") -> None:
        """Bulk insert DataFrame rows with pyodbc fast_executemany."""
        if dataframe.empty:
            return
        columns = list(dataframe.columns)
        placeholders = ", ".join("?" for _ in columns)
        column_list = ", ".join(quote_sqlserver_identifier(column) for column in columns)
        sql = f"INSERT INTO {sqlserver_qualified_name(schema, table)} ({column_list}) VALUES ({placeholders})"
        rows = [
            tuple(sqlserver_value(value) for value in row)
            for row in dataframe.itertuples(index=False, name=None)
        ]
        cursor.fast_executemany = True
        cursor.executemany(sql, rows)


def quote_sqlserver_identifier(identifier: str) -> str:
    """Quote and validate a SQL Server identifier."""
    if not VALID_IDENTIFIER.match(identifier):
        raise DatabaseError(
            f"Invalid SQL Server identifier '{identifier}'. Use letters, numbers and underscores; do not start with a number."
        )
    return f"[{identifier}]"


def sqlserver_qualified_name(schema: str, table: str) -> str:
    """Return a quoted SQL Server schema-qualified table name."""
    return f"{quote_sqlserver_identifier(schema)}.{quote_sqlserver_identifier(table)}"


def sqlserver_connection_string(config: DatabaseConnectionConfig) -> str:
    """Build a pyodbc connection string for SQL Server."""
    parts = [
        f"DRIVER={{{config.driver}}}",
        f"SERVER={config.host},{config.port}",
        f"DATABASE={config.database}",
        f"Encrypt={'yes' if config.encrypt else 'no'}",
        f"TrustServerCertificate={'yes' if config.trust_server_certificate else 'no'}",
    ]
    if config.trusted_connection:
        parts.append("Trusted_Connection=yes")
    else:
        parts.extend([f"UID={config.user}", f"PWD={config.password}"])
    return ";".join(parts)


def sqlserver_create_schema_sql(schema: str) -> str:
    """Return idempotent SQL Server schema creation SQL."""
    quote_sqlserver_identifier(schema)
    escaped = schema.replace("'", "''")
    return f"IF SCHEMA_ID(N'{escaped}') IS NULL EXEC(N'CREATE SCHEMA {quote_sqlserver_identifier(schema)}')"


def sqlserver_drop_table_sql(schema: str, table: str) -> str:
    """Return idempotent SQL Server table drop SQL."""
    return f"IF OBJECT_ID(N'{schema}.{table}', N'U') IS NOT NULL DROP TABLE {sqlserver_qualified_name(schema, table)}"


def sqlserver_value(value: Any) -> Any:
    """Convert pandas missing values to None for pyodbc."""
    try:
        import pandas as pd
    except ImportError:
        pd = None
    if pd is not None and pd.isna(value):
        return None
    return value


def ensure_sqlserver_unique_index(cursor: Any, schema: str, table: str, columns: list[str]) -> None:
    """Create a deterministic unique index for SQL Server upsert conflict keys."""
    for column in columns:
        quote_sqlserver_identifier(column)
    suffix = hashlib.md5("|".join(columns).encode("utf-8")).hexdigest()[:8]
    index_name = f"{table[:48]}_{suffix}_uidx"
    column_list = ", ".join(quote_sqlserver_identifier(column) for column in columns)
    cursor.execute(
        f"""
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = ? AND object_id = OBJECT_ID(?)
        )
        CREATE UNIQUE INDEX {quote_sqlserver_identifier(index_name)}
        ON {sqlserver_qualified_name(schema, table)} ({column_list})
        """,
        (index_name, f"{schema}.{table}"),
    )
