import os
import re
import unittest


RELEASE_VERSION = "0.4.0"
INSTALLER_NAME = f"ColorComic-Setup-{RELEASE_VERSION}-win64-cpu.exe"


class ReleaseVersionDocsTests(unittest.TestCase):
    def read_file(self, *parts):
        root = os.getcwd()
        with open(os.path.join(root, *parts), encoding="utf-8") as handle:
            return handle.read()

    def test_inno_version_matches_current_release(self):
        script = self.read_file("packaging", "inno", "ColorComic.iss")

        self.assertIn(f'#define MyAppVersion "{RELEASE_VERSION}"', script)
        self.assertIn("OutputBaseFilename=ColorComic-Setup-{#MyAppVersion}-win64-cpu", script)

    def test_installer_filename_references_match_current_release(self):
        paths = [
            ("packaging", "README.md"),
            ("packaging", "VALIDATION.md"),
            ("packaging", "RELEASE_NOTES.md"),
            ("packaging", "build_installer.ps1"),
        ]

        for parts in paths:
            with self.subTest(path=os.path.join(*parts)):
                self.assertIn(INSTALLER_NAME, self.read_file(*parts))

    def test_release_notes_latest_section_matches_current_release(self):
        notes = self.read_file("packaging", "RELEASE_NOTES.md")
        headings = re.findall(r"^## (v[0-9]+\.[0-9]+\.[0-9]+)", notes, flags=re.MULTILINE)

        self.assertGreaterEqual(len(headings), 1)
        self.assertEqual(headings[0], f"v{RELEASE_VERSION}")

    def test_readme_mentions_current_release_summary(self):
        readme = self.read_file("README.md")

        self.assertIn("## v0.4.0 Summary", readme)
        self.assertIn("workflow", readme)

    def test_packaging_docs_cover_batch_validation(self):
        validation = self.read_file("packaging", "VALIDATION.md")
        packaging_readme = self.read_file("packaging", "README.md")

        for expected in (
            "Batch processing",
            "Start Batch",
            "queued",
            "cancelled",
            "Recent Outputs shows completed batch jobs",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, validation)

        self.assertIn("tests.test_batch_queue", packaging_readme)
        self.assertIn("core\\batch_queue.py", packaging_readme)

    def test_pyinstaller_spec_includes_batch_queue_helper(self):
        spec = self.read_file("packaging", "ColorComic.spec")

        self.assertIn('"core.batch_queue"', spec)

    def test_packaging_docs_cover_v040_workflow_validation(self):
        validation = self.read_file("packaging", "VALIDATION.md")
        packaging_readme = self.read_file("packaging", "README.md")

        for expected in (
            "Processing page clarity",
            "Recent Outputs removal",
            "Batch setup preview/removal workflow",
            "Auto-only batch messaging",
            "Preferences reset",
            "Accessibility",
            "Responsive layout smoke checks",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, validation)

        self.assertIn("tests.test_responsive_layout_css", packaging_readme)
        self.assertIn("v0.4.0 workflow-polish focused tests", packaging_readme)


if __name__ == "__main__":
    unittest.main()
