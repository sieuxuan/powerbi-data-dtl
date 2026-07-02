from __future__ import annotations

import importlib.util
import unittest

from core.schema_compare import ColumnInfo, compare_columns, compare_dataframe_to_columns, compare_schema, normalize_identifier


class FakeCursor:
    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        return None

    def execute(self, _query: str, params: tuple[str, str]) -> None:
        self.params = params

    def fetchall(self) -> list[tuple[str, str, str]]:
        return [
            ("id", "bigint", "NO"),
            ("name", "text", "YES"),
            ("amount", "text", "YES"),
        ]


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


class SchemaCompareTests(unittest.TestCase):
    def test_normalize_identifier(self) -> None:
        self.assertEqual(normalize_identifier(" Doanh thu 2026 "), "doanh_thu_2026")
        self.assertEqual(normalize_identifier("123"), "column_123")

    def test_compare_columns(self) -> None:
        result = compare_columns(
            ["id", "name", "amount"],
            [
                ColumnInfo(name="id", data_type="bigint", is_nullable=False),
                ColumnInfo(name="name", data_type="text", is_nullable=True),
                ColumnInfo(name="old_col", data_type="text", is_nullable=True),
            ],
        )
        self.assertTrue(result.has_mismatch)
        self.assertEqual(result.missing_in_db, ["amount"])
        self.assertEqual(result.extra_in_db, ["old_col"])

    @unittest.skipIf(importlib.util.find_spec("pandas") is None, "pandas is not installed")
    def test_compare_schema_accepts_schema_qualified_table(self) -> None:
        import pandas as pd

        dataframe = pd.DataFrame({"ID": [1], "Name": ["A"], "Amount": [10.5]})
        connection = FakeConnection()

        result = compare_schema(connection, "public.sample", dataframe)

        self.assertTrue(result.match)
        self.assertEqual(connection.cursor_instance.params, ("public", "sample"))
        self.assertEqual(result.type_mismatches, [])

    @unittest.skipIf(importlib.util.find_spec("pandas") is None, "pandas is not installed")
    def test_compare_dataframe_to_columns_flags_type_mismatch(self) -> None:
        import pandas as pd

        dataframe = pd.DataFrame({"id": [1], "active": [True]})
        result = compare_dataframe_to_columns(
            dataframe,
            [
                ColumnInfo(name="id", data_type="bigint", is_nullable=False),
                ColumnInfo(name="active", data_type="timestamp without time zone", is_nullable=True),
            ],
        )

        self.assertTrue(result.has_mismatch)
        self.assertEqual(result.type_mismatches[0]["col"], "active")

    @unittest.skipIf(importlib.util.find_spec("pandas") is None, "pandas is not installed")
    def test_compare_dataframe_to_sqlserver_columns_uses_sqlserver_types(self) -> None:
        import pandas as pd

        dataframe = pd.DataFrame(
            {
                "id": [1],
                "active": [True],
                "created_at": pd.to_datetime(["2026-01-01"]),
            }
        )
        result = compare_dataframe_to_columns(
            dataframe,
            [
                ColumnInfo(name="id", data_type="bigint", is_nullable=False),
                ColumnInfo(name="active", data_type="bit", is_nullable=True),
                ColumnInfo(name="created_at", data_type="datetime2", is_nullable=True),
            ],
            engine="sqlserver",
        )

        self.assertTrue(result.match)
        self.assertEqual(result.type_mismatches, [])


if __name__ == "__main__":
    unittest.main()
