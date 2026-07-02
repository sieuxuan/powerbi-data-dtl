"""So sánh schema DataFrame với bảng SQL target và chuẩn hóa tên cột."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


IDENTIFIER_PATTERN = re.compile(r"[^0-9A-Za-z_]+")


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    is_nullable: bool


@dataclass(frozen=True)
class SchemaCompareResult:
    table_exists: bool
    match: bool
    missing_in_db: list[str] = field(default_factory=list)
    extra_in_db: list[str] = field(default_factory=list)
    type_mismatches: list[dict[str, str]] = field(default_factory=list)

    @property
    def has_mismatch(self) -> bool:
        """Return whether the comparison found missing or extra columns."""
        return bool(self.missing_in_db or self.extra_in_db or self.type_mismatches)


def compare_columns(dataframe_columns: list[str], db_columns: list[ColumnInfo] | None) -> SchemaCompareResult:
    """Compare normalized DataFrame columns with target table columns."""
    if db_columns is None:
        return SchemaCompareResult(table_exists=False, match=False)

    excel_cols = set(dataframe_columns)
    database_cols = {column.name for column in db_columns}
    missing_in_db = sorted(excel_cols - database_cols)
    extra_in_db = sorted(database_cols - excel_cols)

    return SchemaCompareResult(
        table_exists=True,
        match=not missing_in_db and not extra_in_db,
        missing_in_db=missing_in_db,
        extra_in_db=extra_in_db,
    )


def compare_dataframe_to_columns(
    df: "pd.DataFrame",
    db_columns: list[ColumnInfo] | None,
    *,
    engine: str = "postgresql",
) -> SchemaCompareResult:
    """Compare DataFrame columns and broad types against target column metadata."""
    if db_columns is None:
        return SchemaCompareResult(table_exists=False, match=False)
    if not db_columns:
        return SchemaCompareResult(table_exists=False, match=False)

    normalized_columns = [
        normalize_identifier(column, f"column_{index + 1}")
        for index, column in enumerate(df.columns)
    ]
    result = compare_columns(normalized_columns, db_columns)
    db_types = {column.name: column.data_type for column in db_columns}
    type_mismatches: list[dict[str, str]] = []
    for source_column, normalized_column in zip(df.columns, normalized_columns, strict=True):
        db_type = db_types.get(normalized_column)
        if db_type is None:
            continue
        source_type = _target_type_name_for_series(df[source_column], engine)
        if not _types_compatible(source_type, db_type, engine):
            type_mismatches.append(
                {
                    "col": normalized_column,
                    "excel_type": source_type,
                    "db_type": db_type,
                }
            )

    return SchemaCompareResult(
        table_exists=True,
        match=result.match and not type_mismatches,
        missing_in_db=result.missing_in_db,
        extra_in_db=result.extra_in_db,
        type_mismatches=type_mismatches,
    )


def compare_schema(
    conn: object,
    table_name: str,
    df: "pd.DataFrame",
    schema: str = "public",
) -> SchemaCompareResult:
    """Compare DataFrame columns and broad types against an existing PostgreSQL table."""
    table_schema, table = _split_table_name(table_name, schema)
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table_schema, table),
        )
        db_columns = [
            ColumnInfo(name=row[0], data_type=row[1], is_nullable=row[2] == "YES")
            for row in cursor.fetchall()
        ]

    if not db_columns:
        return SchemaCompareResult(table_exists=False, match=False)

    return compare_dataframe_to_columns(df, db_columns)


def normalize_identifier(value: object, fallback: str = "column") -> str:
    """Convert a string into a SQL-friendly identifier."""
    normalized = str(value).strip().lower()
    normalized = IDENTIFIER_PATTERN.sub("_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        normalized = fallback
    if normalized[0].isdigit():
        normalized = f"{fallback}_{normalized}"
    return normalized[:63]


def normalize_dataframe_columns(dataframe: "pd.DataFrame") -> "pd.DataFrame":
    """Return a DataFrame copy with SQL-friendly unique column names."""
    normalized = dataframe.copy()
    normalized.columns = dedupe_identifiers(
        [
            normalize_identifier(column, f"column_{index + 1}")
            for index, column in enumerate(dataframe.columns)
        ]
    )
    return normalized


def dedupe_identifiers(columns: list[str]) -> list[str]:
    """Ensure normalized identifiers are unique."""
    seen: dict[str, int] = {}
    result: list[str] = []
    for column in columns:
        count = seen.get(column, 0) + 1
        seen[column] = count
        if count == 1:
            result.append(column)
        else:
            suffix = f"_{count}"
            result.append(f"{column[: 63 - len(suffix)]}{suffix}")
    return result


def _split_table_name(table_name: str, default_schema: str) -> tuple[str, str]:
    """Split optional schema.table input into schema and table names."""
    parts = [part.strip('" ') for part in table_name.split(".", 1)]
    if len(parts) == 2 and parts[0] and parts[1]:
        return normalize_identifier(parts[0], "schema"), normalize_identifier(parts[1], "table")
    return normalize_identifier(default_schema, "schema"), normalize_identifier(table_name, "table")


def _target_type_name_for_series(series: "pd.Series", engine: str) -> str:
    """Map a pandas Series dtype to the target engine type name for comparison."""
    try:
        from pandas.api import types as pd_types
    except ImportError:
        return "text"

    if pd_types.is_bool_dtype(series):
        return "bit" if engine == "sqlserver" else "boolean"
    if pd_types.is_integer_dtype(series):
        return "bigint"
    if pd_types.is_float_dtype(series):
        return "float" if engine == "sqlserver" else "double precision"
    if pd_types.is_datetime64_any_dtype(series):
        return "datetime2" if engine == "sqlserver" else "timestamp without time zone"
    return "nvarchar" if engine == "sqlserver" else "text"


def _types_compatible(source_type: str, db_type: str, engine: str = "postgresql") -> bool:
    """Return whether source and database types are close enough for import."""
    source_group = _type_group(source_type, engine)
    db_group = _type_group(db_type, engine)
    if source_group == "text" or db_group == "text":
        return True
    return source_group == db_group


def _type_group(type_name: str, engine: str = "postgresql") -> str:
    """Collapse target SQL type aliases into broad comparable groups."""
    normalized = type_name.lower()
    if engine == "sqlserver":
        if normalized in {"bigint", "int", "integer", "smallint", "tinyint"}:
            return "integer"
        if normalized in {"float", "real", "numeric", "decimal", "money", "smallmoney"}:
            return "float"
        if normalized == "bit":
            return "boolean"
        if normalized in {"date", "datetime", "datetime2", "smalldatetime", "time", "datetimeoffset"}:
            return "datetime"
        if normalized in {"varchar", "nvarchar", "text", "ntext", "char", "nchar", "xml", "uniqueidentifier"}:
            return "text"
        return "text"
    if normalized in {"bigint", "integer", "int", "smallint", "serial", "bigserial"}:
        return "integer"
    if normalized in {"double precision", "real", "numeric", "decimal"}:
        return "float"
    if normalized in {"boolean", "bool"}:
        return "boolean"
    if normalized.startswith("timestamp") or normalized in {"date", "time without time zone", "time with time zone"}:
        return "datetime"
    return "text"
