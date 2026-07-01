from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from core.config import ConfigError, load_config


@unittest.skipIf(importlib.util.find_spec("yaml") is None, "PyYAML is not installed")
class ConfigTests(unittest.TestCase):
    def test_upsert_requires_primary_key(self) -> None:
        config_text = """
database:
  host: localhost
  name: powerbi_data
  user: postgres
files:
  - name: sample
    source:
      type: local
      path: sample.csv
    target:
      table: sample
    sync_mode: upsert
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.yaml"
            path.write_text(config_text, encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_extended_defaults_are_loaded(self) -> None:
        config_text = """
database:
  host: localhost
  name: powerbi_data
  user: postgres
files: []
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.yaml"
            path.write_text(config_text, encoding="utf-8")
            config = load_config(path)
            self.assertEqual(config.api.port, 8765)
            self.assertEqual(config.retry.db.attempts, 3)
            self.assertFalse(config.updates.enabled)
            self.assertTrue(config.logging.log_to_db)

    def test_updates_are_loaded(self) -> None:
        config_text = """
database:
  host: localhost
  name: powerbi_data
  user: postgres
updates:
  enabled: true
  repo: example/powerbi-data-dtl
  current_version: "1.2.3"
  asset_pattern: portable.zip
  auto_download: true
  auto_apply: true
files: []
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.yaml"
            path.write_text(config_text, encoding="utf-8")
            config = load_config(path)
            self.assertTrue(config.updates.enabled)
            self.assertEqual(config.updates.repo, "example/powerbi-data-dtl")
            self.assertEqual(config.updates.current_version, "1.2.3")
            self.assertEqual(config.updates.asset_pattern, "portable.zip")
            self.assertTrue(config.updates.auto_download)
            self.assertTrue(config.updates.auto_apply)

    def test_null_sheet_defaults_to_first_sheet(self) -> None:
        config_text = """
database:
  host: localhost
  name: powerbi_data
  user: postgres
files:
  - name: sample
    source:
      type: local
      path: sample.xlsx
    target:
      table: sample
    options:
      sheet: null
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.yaml"
            path.write_text(config_text, encoding="utf-8")
            config = load_config(path)
            self.assertEqual(config.files[0].options.sheet, 0)

    def test_column_renames_and_webhook_are_loaded(self) -> None:
        config_text = """
database:
  host: localhost
  name: powerbi_data
  user: postgres
files:
  - name: sample
    source:
      type: local
      path: sample.csv
    target:
      table: sample
    options:
      skip_columns:
        - "Ghi chú"
      column_renames:
        "Mã KH": "ma_kh"
notifications:
  webhook:
    enabled: true
    url: "https://example.test/webhook"
    timeout_seconds: 5
    statuses:
      - success
      - failed
      - mismatch
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.yaml"
            path.write_text(config_text, encoding="utf-8")
            config = load_config(path)
            self.assertEqual(config.files[0].options.skip_columns, ["Ghi chú"])
            self.assertEqual(config.files[0].options.column_renames["Mã KH"], "ma_kh")
            self.assertTrue(config.notifications.webhook.enabled)
            self.assertEqual(config.notifications.webhook.url, "https://example.test/webhook")
            self.assertEqual(config.notifications.webhook.timeout_seconds, 5)
            self.assertEqual(config.notifications.webhook.statuses, ["success", "failed", "mismatch"])

    def test_multiple_crons_are_loaded(self) -> None:
        config_text = """
database:
  host: localhost
  name: powerbi_data
  user: postgres
files:
  - name: sample
    source:
      type: local
      path: sample.csv
    target:
      table: sample
    cron: "0 6 * * *"
    crons:
      - "0 6 * * *"
      - "30 13 * * *"
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.yaml"
            path.write_text(config_text, encoding="utf-8")
            config = load_config(path)
            self.assertEqual(config.files[0].cron, "0 6 * * *")
            self.assertEqual(config.files[0].crons, ["0 6 * * *", "30 13 * * *"])

    def test_invalid_cron_is_rejected(self) -> None:
        config_text = """
database:
  host: localhost
  name: powerbi_data
  user: postgres
files:
  - name: sample
    source:
      type: local
      path: sample.csv
    target:
      table: sample
    crons:
      - "bad cron"
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.yaml"
            path.write_text(config_text, encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
