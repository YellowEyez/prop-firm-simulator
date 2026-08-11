import unittest
from pathlib import Path

from starbase_paths import APP_DIR, asset_path, existing_asset


class TestStarBasePaths(unittest.TestCase):
    def test_asset_path_is_absolute_and_app_relative(self):
        p = asset_path("logo_dark.png")
        self.assertTrue(p.is_absolute())
        self.assertEqual(p.parent, APP_DIR)

    def test_packaged_logos_exist(self):
        self.assertIsNotNone(existing_asset("logo_dark.png"))
        self.assertIsNotNone(existing_asset("logo_light.png"))

    def test_missing_asset_returns_none(self):
        self.assertIsNone(existing_asset("definitely_not_a_real_asset.xyz"))


if __name__ == "__main__":
    unittest.main()
