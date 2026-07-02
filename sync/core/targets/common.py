"""Common SQL target protocols and helpers."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Protocol

from ..config import DatabaseConfig, DatabaseConnectionConfig
from ..schema_compare import ColumnInfo

if TYPE_CHECKING:
    import pandas as pd


VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


class DatabaseError(RuntimeError):
    """Raised when a SQL target operation fails."""


class SqlTargetClient(Protocol):
    """Common operations required by a SQL import target."""

    config: DatabaseConnectionConfig | DatabaseConfig

    def test_connection(self) -> None: ...
    def test_write_permission(self, schema: str) -> None: ...
    def table_exists(self, schema: str, table: str) -> bool: ...
    def get_columns(self, schema: str, table: str) -> list[ColumnInfo]: ...
    def replace_table(
        self,
        schema: str,
        table: str,
        dataframe: "pd.DataFrame",
        unique_columns: list[str] | None = None,
    ) -> int: ...
    def truncate_insert(self, schema: str, table: str, dataframe: "pd.DataFrame") -> int: ...
    def append_insert(self, schema: str, table: str, dataframe: "pd.DataFrame") -> int: ...
    def upsert_insert(self, schema: str, table: str, dataframe: "pd.DataFrame", primary_key: list[str]) -> int: ...
    def close(self) -> None: ...


def validate_upsert_dataframe(dataframe: "pd.DataFrame", primary_key: list[str]) -> None:
    """Validate upsert primary key columns before touching a SQL target."""
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


def infer_dataframe_schema(dataframe: "pd.DataFrame", engine: str = "postgresql") -> list[dict[str, Any]]:
    """Return target SQL type preview for a DataFrame."""
    columns: list[dict[str, Any]] = []
    for column in dataframe.columns:
        series = dataframe[column]
        sample = ""
        for value in series.dropna().head(1).tolist():
            sample = str(value)
            break
        target_type = (
            sqlserver_type_for_series(series)
            if engine == "sqlserver"
            else postgres_type_for_series(series)
        )
        columns.append(
            {
                "name": str(column),
                "pandas_type": str(series.dtype),
                "postgres_type": target_type,
                "target_type": target_type,
                "nullable": bool(series.isna().any()),
                "sample": sample,
            }
        )
    return columns


def connection_database(config: DatabaseConfig | DatabaseConnectionConfig) -> str:
    """Return database name from legacy or named connection config."""
    return getattr(config, "name", getattr(config, "database", ""))


def postgres_type_for_series(series: "pd.Series") -> str:
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


def sqlserver_type_for_series(series: "pd.Series") -> str:
    """Map a pandas Series dtype to a SQL Server type."""
    try:
        from pandas.api import types as pd_types
    except ImportError as exc:
        raise DatabaseError("pandas is required for dtype mapping.") from exc

    if pd_types.is_bool_dtype(series):
        return "BIT"
    if pd_types.is_integer_dtype(series):
        return "BIGINT"
    if pd_types.is_float_dtype(series):
        return "FLOAT"
    if pd_types.is_datetime64_any_dtype(series):
        return "DATETIME2"
    return "NVARCHAR(MAX)"


def log_row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
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
