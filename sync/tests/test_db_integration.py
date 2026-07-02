from __future__ import annotations

import os
import unittest
import uuid

import pandas as pd

from core.config import DatabaseConnectionConfig
from core.db import PostgresClient, SqlServerClient
from core.targets.postgres import qualified_name
from core.targets.sqlserver import sqlserver_drop_table_sql, sqlserver_qualified_name


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _postgres_config() -> DatabaseConnectionConfig | None:
    host = os.environ.get("SYNC_TEST_PG_HOST")
    database = os.environ.get("SYNC_TEST_PG_DATABASE")
    user = os.environ.get("SYNC_TEST_PG_USER")
    if not (host and database and user):
        return None
    return DatabaseConnectionConfig(
        id="integration_pg",
        name="Integration PostgreSQL",
        engine="postgresql",
        host=host,
        port=int(os.environ.get("SYNC_TEST_PG_PORT", "5432")),
        database=database,
        user=user,
        password=os.environ.get("SYNC_TEST_PG_PASSWORD", ""),
        schema="public",
    )


def _sqlserver_config() -> DatabaseConnectionConfig | None:
    host = os.environ.get("SYNC_TEST_MSSQL_HOST")
    database = os.environ.get("SYNC_TEST_MSSQL_DATABASE")
    if not (host and database):
        return None
    trusted = _env_bool("SYNC_TEST_MSSQL_TRUSTED_CONNECTION", False)
    user = os.environ.get("SYNC_TEST_MSSQL_USER", "")
    if not trusted and not user:
        return None
    return DatabaseConnectionConfig(
        id="integration_mssql",
        name="Integration SQL Server",
        engine="sqlserver",
        host=host,
        port=int(os.environ.get("SYNC_TEST_MSSQL_PORT", "1433")),
        database=database,
        user=user,
        password=os.environ.get("SYNC_TEST_MSSQL_PASSWORD", ""),
        schema="dbo",
        driver=os.environ.get("SYNC_TEST_MSSQL_DRIVER", "ODBC Driver 18 for SQL Server"),
        trusted_connection=trusted,
        encrypt=_env_bool("SYNC_TEST_MSSQL_ENCRYPT", True),
        trust_server_certificate=_env_bool("SYNC_TEST_MSSQL_TRUST_SERVER_CERTIFICATE", True),
    )


@unittest.skipUnless(_postgres_config(), "Set SYNC_TEST_PG_* env vars to run PostgreSQL integration tests")
class PostgresIntegrationTests(unittest.TestCase):
    def test_replace_and_upsert_roundtrip(self) -> None:
        config = _postgres_config()
        assert config is not None
        schema = f"sync_it_{uuid.uuid4().hex[:8]}"
        table = "sales"
        client = PostgresClient(config)
        try:
            client.replace_table(schema, table, pd.DataFrame({"id": [1, 2], "amount": [10.5, 20.0]}), ["id"])
            self.assertTrue(client.table_exists(schema, table))
            self.assertEqual(client.upsert_insert(schema, table, pd.DataFrame({"id": [2, 3], "amount": [25.0, 30.0]}), ["id"]), 2)
            with client.connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(f"SELECT COUNT(*), SUM(amount) FROM {qualified_name(schema, table)}")
                    count, total = cursor.fetchone()
            self.assertEqual(count, 3)
            self.assertAlmostEqual(float(total), 65.5)
        finally:
            with client.connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(f"DROP SCHEMA IF EXISTS {qualified_name(schema, table).split('.')[0]} CASCADE")
                connection.commit()
            client.close()


@unittest.skipUnless(_sqlserver_config(), "Set SYNC_TEST_MSSQL_* env vars to run SQL Server integration tests")
class SqlServerIntegrationTests(unittest.TestCase):
    def test_replace_and_upsert_roundtrip(self) -> None:
        config = _sqlserver_config()
        assert config is not None
        schema = f"sync_it_{uuid.uuid4().hex[:8]}"
        table = "sales"
        client = SqlServerClient(config)
        try:
            client.replace_table(schema, table, pd.DataFrame({"id": [1, 2], "amount": [10.5, 20.0]}), ["id"])
            self.assertTrue(client.table_exists(schema, table))
            self.assertEqual(client.upsert_insert(schema, table, pd.DataFrame({"id": [2, 3], "amount": [25.0, 30.0]}), ["id"]), 2)
            with client.connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(f"SELECT COUNT(*), SUM([amount]) FROM {sqlserver_qualified_name(schema, table)}")
                    count, total = cursor.fetchone()
            self.assertEqual(count, 3)
            self.assertAlmostEqual(float(total), 65.5)
        finally:
            with client.connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(sqlserver_drop_table_sql(schema, table))
                    cursor.execute(f"IF SCHEMA_ID(N'{schema}') IS NOT NULL EXEC(N'DROP SCHEMA [{schema}]')")
                connection.commit()


if __name__ == "__main__":
    unittest.main()
