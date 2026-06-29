from __future__ import annotations

import importlib.util
import unittest

from core.file_reader import _apply_column_renames, _clean_dataframe, _drop_skipped_columns


@unittest.skipIf(importlib.util.find_spec("pandas") is None, "pandas is not installed")
class FileReaderCleaningTests(unittest.TestCase):
    def test_clean_dataframe_drops_empty_edge_columns(self) -> None:
        import pandas as pd

        dataframe = pd.DataFrame(
            {
                "Unnamed: 0": [None, None],
                " Name ": ["A", "B"],
                "Amount": [10, 20],
                "Unnamed: 3": [None, None],
            }
        )

        cleaned = _clean_dataframe(dataframe)

        self.assertEqual(list(cleaned.columns), ["Name", "Amount"])

    def test_clean_dataframe_keeps_blank_header_with_values(self) -> None:
        import pandas as pd

        dataframe = pd.DataFrame({"Unnamed: 0": ["x"], "Name": ["A"]})

        cleaned = _clean_dataframe(dataframe)

        self.assertEqual(list(cleaned.columns), ["column_1", "Name"])

    def test_apply_column_renames_after_header_cleanup(self) -> None:
        import pandas as pd

        dataframe = pd.DataFrame({" Ma KH ": ["A01"], "Doanh thu": [10]})
        cleaned = _clean_dataframe(dataframe)
        renamed = _apply_column_renames(cleaned, {"Ma KH": "ma_kh", "Doanh thu": "doanh_thu"})

        self.assertEqual(list(renamed.columns), ["ma_kh", "doanh_thu"])

    def test_drop_skipped_columns_after_header_cleanup(self) -> None:
        import pandas as pd

        dataframe = pd.DataFrame({"Buyer": ["A"], "Buyer.1": ["B"], "Amount": [10]})
        cleaned = _clean_dataframe(dataframe)
        filtered = _drop_skipped_columns(cleaned, ["Buyer.1"])

        self.assertEqual(list(filtered.columns), ["Buyer", "Amount"])


if __name__ == "__main__":
    unittest.main()
