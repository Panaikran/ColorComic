import os
import unittest


class IconAssetTests(unittest.TestCase):
    def test_canonical_icon_asset_and_references_exist(self):
        root = os.getcwd()
        icon_path = os.path.join(root, "static", "img", "colorcomic.ico")

        self.assertTrue(os.path.isfile(icon_path))
        self.assertGreater(os.path.getsize(icon_path), 0)

        with open(os.path.join(root, "templates", "base.html"), encoding="utf-8") as handle:
            base_template = handle.read()
        self.assertIn("img/colorcomic.ico", base_template)

        with open(os.path.join(root, "packaging", "ColorComic.spec"), encoding="utf-8") as handle:
            spec = handle.read()
        self.assertIn("colorcomic.ico", spec)
        self.assertIn("icon=str(APP_ICON)", spec)

        with open(os.path.join(root, "packaging", "inno", "ColorComic.iss"), encoding="utf-8") as handle:
            installer = handle.read()
        self.assertIn('#define MyAppVersion "0.6.0"', installer)
        self.assertIn("SetupIconFile={#MyAppIcon}", installer)


if __name__ == "__main__":
    unittest.main()
