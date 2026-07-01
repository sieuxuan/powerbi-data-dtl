from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.config import UpdateConfig
from core.updater import check_for_update, download_update


class UpdaterTests(unittest.TestCase):
    def test_check_reports_existing_versioned_download(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            download_dir = base_dir / "downloads" / "updates"
            download_dir.mkdir(parents=True)
            existing = download_dir / "PowerBIDataDTL-portable-1.2.0.zip"
            existing.write_bytes(b"zip")

            config = UpdateConfig(
                enabled=True,
                repo="example/repo",
                current_version="1.1.0",
                asset_pattern="PowerBIDataDTL-portable.zip",
            )

            with patch("core.updater._fetch_latest_release", return_value=_release()):
                info = check_for_update(config, base_dir)

            self.assertTrue(info.update_available)
            self.assertEqual(info.downloaded_path, str(existing))

    def test_download_reuses_existing_versioned_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            download_dir = base_dir / "downloads" / "updates"
            download_dir.mkdir(parents=True)
            existing = download_dir / "PowerBIDataDTL-portable-1.2.0.zip"
            existing.write_bytes(b"zip")

            config = UpdateConfig(
                enabled=True,
                repo="example/repo",
                current_version="1.1.0",
                asset_pattern="PowerBIDataDTL-portable.zip",
            )

            with patch("core.updater._fetch_latest_release", return_value=_release()):
                info = download_update(config, base_dir)

            self.assertEqual(info.downloaded_path, str(existing))
            self.assertIn("already downloaded", info.message)


def _release() -> dict[str, object]:
    return {
        "tag_name": "v1.2.0",
        "html_url": "https://github.com/example/repo/releases/tag/v1.2.0",
        "assets": [
            {
                "name": "PowerBIDataDTL-portable.zip",
                "browser_download_url": "https://example.test/PowerBIDataDTL-portable.zip",
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
