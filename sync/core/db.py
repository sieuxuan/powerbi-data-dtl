"""Compatibility exports for SQL target adapters."""

from __future__ import annotations

from .config import DatabaseConnectionConfig
from .targets.common import (
    DatabaseError,
    SqlTargetClient,
    infer_dataframe_schema,
    postgres_type_for_series as _postgres_type_for_series,
    sqlserver_type_for_series as _sqlserver_type_for_series,
    validate_upsert_dataframe,
)
from .targets.postgres import PostgresClient, qualified_name, quote_identifier
from .targets.sqlserver import (
    SqlServerClient,
    quote_sqlserver_identifier,
    sqlserver_connection_string as _sqlserver_connection_string,
    sqlserver_qualified_name,
)


def create_sql_target_client(config: DatabaseConnectionConfig) -> SqlTargetClient:
    """Create a SQL target client for a named connection."""
    if config.engine == "postgresql":
        return PostgresClient(config)
    if config.engine == "sqlserver":
        return SqlServerClient(config)
    raise DatabaseError(f"Unsupported database engine: {config.engine}")


__all__ = [
    "DatabaseError",
    "PostgresClient",
    "SqlServerClient",
    "SqlTargetClient",
    "_postgres_type_for_series",
    "_sqlserver_connection_string",
    "_sqlserver_type_for_series",
    "create_sql_target_client",
    "infer_dataframe_schema",
    "qualified_name",
    "quote_identifier",
    "quote_sqlserver_identifier",
    "sqlserver_qualified_name",
    "validate_upsert_dataframe",
]
