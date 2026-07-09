import os
import re
import unittest


RELEASE_VERSION = "0.5.0"
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

        self.assertIn("## v0.5.0 Summary", readme)
        self.assertIn("diagnostics", readme)

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

    def test_cuda_development_path_is_documented_as_experimental(self):
        root = os.getcwd()
        readme = self.read_file("README.md")
        packaging_readme = self.read_file("packaging", "README.md")

        self.assertTrue(os.path.exists(os.path.join(root, "requirements-windows-cuda-experimental.txt")))
        self.assertIn("Experimental CUDA Development", readme)
        self.assertIn("official Windows desktop release remains CPU-only", readme)
        self.assertIn("unsupported for released installers", readme)
        self.assertIn("requirements-windows-cuda-experimental.txt", readme)
        self.assertIn("official Windows installer is CPU-only", packaging_readme)
        self.assertIn("source-based developer CUDA experiments", packaging_readme)

    def test_cuda_build_plan_keeps_cpu_release_official(self):
        plan = self.read_file("packaging", "CUDA_BUILD_PLAN.md")
        packaging_readme = self.read_file("packaging", "README.md")

        for expected in (
            "Keep v0.5.0 CPU-only.",
            "separate CUDA preview installer in v0.6.0 or later",
            "Do not use a unified installer yet.",
            "driver `531.14`",
            "or newer",
            "Auto mode: recommend at least 4 GB VRAM",
            "Reference mode: recommend at least 8 GB VRAM",
            "CUDA runtime DLLs",
            "PyInstaller",
            "multiple gigabytes",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, plan)

        self.assertIn("packaging\\CUDA_BUILD_PLAN.md", packaging_readme)

    def test_packaging_docs_cover_v050_validation_without_cuda_enablement(self):
        validation = self.read_file("packaging", "VALIDATION.md")
        packaging_readme = self.read_file("packaging", "README.md")

        for expected in (
            "Job timing",
            "page-based ETA",
            "CPU guidance",
            "/api/diagnostics",
            "/api/diagnostics/bundle",
            "Runtime health preflight",
            "Orphan cleanup",
            "Device capability",
            "compute resolution",
            "requirements-windows-cuda-experimental.txt",
            "CUDA installer exists",
            "GPU is selectable in Preferences",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, validation)

        for expected in (
            "v0.5.0 diagnostics, robustness, timing, and device-groundwork tests",
            "tests.test_job_timing",
            "tests.test_diagnostics_bundle",
            "tests.test_runtime_cleanup",
            "tests.test_device_detection",
            "official build resolves to CPU",
            "supported installer remains CPU-only",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, packaging_readme)

        self.assertNotIn("CUDA installer is supported", packaging_readme)
        self.assertNotIn("GPU is selectable in Preferences", packaging_readme)

    def test_release_notes_cover_completed_v050_work_only(self):
        notes = self.read_file("packaging", "RELEASE_NOTES.md")
        latest_section = notes.split("## v0.4.0", 1)[0]

        for expected in (
            "Performance Baseline",
            "job timing",
            "Page-based ETA",
            "/api/diagnostics",
            "/api/diagnostics/bundle",
            "Runtime health preflight",
            "orphaned upload/intermediate cleanup",
            "CPU guidance",
            "Experimental CUDA development",
            "official supported installer remains CPU-only",
            "No CUDA installer is shipped.",
            "ColorComic-Setup-0.5.0-win64-cpu.exe",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, latest_section)

        self.assertNotIn("CUDA installer exists", latest_section)
        self.assertNotIn("auto-updater", latest_section.lower().split("### added", 1)[-1].split("### unchanged", 1)[0])


if __name__ == "__main__":
    unittest.main()
