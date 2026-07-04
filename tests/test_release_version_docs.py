import os
import re
import unittest


RELEASE_VERSION = "0.2.0"
INSTALLER_NAME = f"ColorComic-Setup-{RELEASE_VERSION}-win64-cpu.exe"


class ReleaseVersionDocsTests(unittest.TestCase):
    def read_file(self, *parts):
        root = os.getcwd()
        with open(os.path.join(root, *parts), encoding="utf-8") as handle:
            return handle.read()

    def test_inno_version_matches_v020(self):
        script = self.read_file("packaging", "inno", "ColorComic.iss")

        self.assertIn(f'#define MyAppVersion "{RELEASE_VERSION}"', script)
        self.assertIn("OutputBaseFilename=ColorComic-Setup-{#MyAppVersion}-win64-cpu", script)

    def test_installer_filename_references_match_v020(self):
        paths = [
            ("packaging", "README.md"),
            ("packaging", "VALIDATION.md"),
            ("packaging", "RELEASE_NOTES.md"),
            ("packaging", "build_installer.ps1"),
        ]

        for parts in paths:
            with self.subTest(path=os.path.join(*parts)):
                self.assertIn(INSTALLER_NAME, self.read_file(*parts))

    def test_release_notes_latest_section_is_v020(self):
        notes = self.read_file("packaging", "RELEASE_NOTES.md")
        headings = re.findall(r"^## (v[0-9]+\.[0-9]+\.[0-9]+)", notes, flags=re.MULTILINE)

        self.assertGreaterEqual(len(headings), 1)
        self.assertEqual(headings[0], f"v{RELEASE_VERSION}")

    def test_readme_mentions_v020_summary(self):
        readme = self.read_file("README.md")

        self.assertIn("## v0.2.0 Summary", readme)
        self.assertIn("local workflow hardening release", readme)


if __name__ == "__main__":
    unittest.main()
