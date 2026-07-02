from __future__ import annotations

import importlib.util
import unittest

from core.config import DatabaseConfig, DatabaseConnectionConfig
from core.db import _sqlserver_connection_string, _sqlserver_type_for_series, quote_sqlserver_identifier
from core.targets.common import connection_database


class SqlServerHelperTests(unittest.TestCase):
    def test_quote_sqlserver_identifier(self) -> None:
        self.assertEqual(quote_sqlserver_identifier("dbo"), "[dbo]")
        self.assertEqual(quote_sqlserver_identifier("sales_2026"), "[sales_2026]")

    def test_connection_string_uses_driver_and_security_options(self) -> None:
        config = DatabaseConnectionConfig(
            id="warehouse",
            name="Warehouse",
            engine="sqlserver",
            host="localhost",
            port=1433,
            database="PowerBIData",
            user="sa",
            password="secret",
            schema="dbo",
            driver="ODBC Driver 18 for SQL Server",
            encrypt=True,
            trust_server_certificate=True,
        )

        value = _sqlserver_connection_string(config)

        self.assertIn("DRIVER={ODBC Driver 18 for SQL Server}", value)
        self.assertIn("SERVER=localhost,1433", value)
        self.assertIn("DATABASE=PowerBIData", value)
        self.assertIn("UID=sa", value)
        self.assertIn("PWD=secret", value)
        self.assertIn("Encrypt=yes", value)
        self.assertIn("TrustServerCertificate=yes", value)

    def test_connection_database_prefers_database_over_display_name(self) -> None:
        named_connection = DatabaseConnectionConfig(
            id="default",
            name="PostgreSQL local",
            engine="postgresql",
            host="localhost",
            port=5432,
            database="powerbi_data",
            user="postgres",
            password="secret",
            schema="public",
        )
        legacy_database = DatabaseConfig(
            host="localhost",
            port=5432,
            name="legacy_db",
            user="postgres",
            password="secret",
            schema="public",
        )

        self.assertEqual(connection_database(named_connection), "powerbi_data")
        self.assertEqual(connection_database(legacy_database), "legacy_db")

    @unittest.skipIf(importlib.util.find_spec("pandas") is None, "pandas is not installed")
    def test_sqlserver_type_mapping(self) -> None:
        import pandas as pd

        self.assertEqual(_sqlserver_type_for_series(pd.Series([1, 2])), "BIGINT")
        self.assertEqual(_sqlserver_type_for_series(pd.Series([1.5, 2.5])), "FLOAT")
        self.assertEqual(_sqlserver_type_for_series(pd.Series([True, False])), "BIT")
        self.assertEqual(_sqlserver_type_for_series(pd.Series(pd.to_datetime(["2026-01-01"]))), "DATETIME2")
        self.assertEqual(_sqlserver_type_for_series(pd.Series(["a", "b"])), "NVARCHAR(MAX)")


if __name__ == "__main__":
    unittest.main()
