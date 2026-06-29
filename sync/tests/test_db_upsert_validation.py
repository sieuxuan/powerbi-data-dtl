from __future__ import annotations

import importlib.util
import unittest

from core.db import DatabaseError, validate_upsert_dataframe


@unittest.skipIf(importlib.util.find_spec("pandas") is None, "pandas is not installed")
class UpsertValidationTests(unittest.TestCase):
    def test_validate_upsert_dataframe_rejects_missing_key(self) -> None:
        import pandas as pd

        dataframe = pd.DataFrame({"id": [1], "name": ["A"]})
        with self.assertRaises(DatabaseError):
            validate_upsert_dataframe(dataframe, ["missing"])

    def test_validate_upsert_dataframe_rejects_duplicate_key(self) -> None:
        import pandas as pd

        dataframe = pd.DataFrame({"id": [1, 1], "name": ["A", "B"]})
        with self.assertRaises(DatabaseError):
            validate_upsert_dataframe(dataframe, ["id"])

    def test_validate_upsert_dataframe_accepts_unique_key(self) -> None:
        import pandas as pd

        dataframe = pd.DataFrame({"id": [1, 2], "name": ["A", "B"]})
        validate_upsert_dataframe(dataframe, ["id"])


if __name__ == "__main__":
    unittest.main()
