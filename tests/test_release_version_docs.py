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

    def test_cuda_build_plan_documents_source_validation_workflow(self):
        plan = self.read_file("packaging", "CUDA_BUILD_PLAN.md")

        for expected in (
            "Source-Mode CUDA Validation Workflow",
            "developer/source validation only",
            "official Windows installer remains CPU-only",
            "requirements-windows-cuda-experimental.txt",
            "scripts\\verify_dependency_imports.py",
            "torch CUDA build",
            "CUDA available",
            "CUDA GPU",
            "tests.test_verify_dependency_imports",
            "tiny one-page PDF",
            "Reference mode only when VRAM is sufficient",
            "Force CPU fallback behavior on a CUDA machine",
            "Do not publish CUDA artifacts",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, plan)

    def test_cuda_build_plan_documents_preview_packaging_path(self):
        root = os.getcwd()
        plan = self.read_file("packaging", "CUDA_BUILD_PLAN.md")

        for expected in (
            "CUDA Preview Packaging Plan",
            "build wrapper",
            "separate from the official CPU",
            "packaging/ColorComicCudaPreview.spec",
            "packaging/build_windows_cuda_preview.ps1",
            "packaging/inno/ColorComicCudaPreview.iss",
            "dist/ColorComicCudaPreview",
            "ColorComic-Setup-0.6.0-win64-cuda-preview.exe",
            "CPU-only Torch wheel",
            "torch.version.cuda",
            "torch.cuda.is_available() is false",
            "model weights",
            "pass CUDA preflight before invoking PyInstaller",
            "preview artifact unless explicitly validated and released",
            "The CPU installer remains official",
            "ColorComic-Setup-{version}-win64-cpu.exe",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, plan)

        self.assertTrue(os.path.exists(os.path.join(root, "packaging", "build_windows_cuda_preview.ps1")))
        self.assertTrue(os.path.exists(os.path.join(root, "packaging", "ColorComicCudaPreview.spec")))
        self.assertTrue(os.path.exists(os.path.join(root, "packaging", "inno", "ColorComicCudaPreview.iss")))

    def test_cuda_preview_build_script_has_safety_preflights(self):
        script = self.read_file("packaging", "build_windows_cuda_preview.ps1")

        for expected in (
            ".venv\\Scripts\\python.exe",
            "Get-Command python",
            "Using Python:",
            "import torch",
            "detect_device_capabilities",
            "torch CUDA build",
            "CUDA available",
            "CUDA GPU",
            "CPU-only Torch is not supported",
            "torch.cuda.is_available() to be true",
            "ColorComicCudaPreview.spec",
            "-m PyInstaller packaging\\ColorComicCudaPreview.spec --clean --noconfirm",
            "dist\\ColorComicCudaPreview\\ColorComicCudaPreview.exe",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, script)

    def test_cuda_preview_spec_is_separate_from_cpu_spec(self):
        cpu_spec = self.read_file("packaging", "ColorComic.spec")
        cuda_spec = self.read_file("packaging", "ColorComicCudaPreview.spec")

        self.assertIn('name="ColorComic"', cpu_spec)
        self.assertIn('name="ColorComicCudaPreview"', cuda_spec)
        self.assertIn("CUDA preview", cuda_spec)
        self.assertNotIn('name="ColorComicCudaPreview"', cpu_spec)

        for forbidden in ("models\\weights", "models/weights", 'include_tree("models"'):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, cuda_spec)

    def test_cuda_preview_inno_script_is_separate_from_cpu_installer(self):
        cpu_inno = self.read_file("packaging", "inno", "ColorComic.iss")
        cuda_inno = self.read_file("packaging", "inno", "ColorComicCudaPreview.iss")

        self.assertIn("OutputBaseFilename=ColorComic-Setup-{#MyAppVersion}-win64-cpu", cpu_inno)
        self.assertIn("OutputBaseFilename=ColorComic-Setup-{#MyAppVersion}-win64-cuda-preview", cuda_inno)
        self.assertIn('#define MyAppName "ColorComic CUDA Preview"', cuda_inno)
        self.assertIn('#define MyAppVersion "0.6.0"', cuda_inno)
        self.assertIn('Source: "..\\..\\dist\\ColorComicCudaPreview\\*"', cuda_inno)
        self.assertIn("Preview only", cuda_inno)
        self.assertIn("%LOCALAPPDATA%\\ColorComic", cuda_inno)
        self.assertIn("model weights out of dist\\ColorComicCudaPreview", cuda_inno)

        self.assertNotIn("win64-cuda-preview", cpu_inno)
        self.assertNotIn("ColorComicCudaPreview", cpu_inno)

    def test_cuda_preview_validation_gate_is_documented(self):
        validation = self.read_file("packaging", "VALIDATION.md")
        plan = self.read_file("packaging", "CUDA_BUILD_PLAN.md")

        for expected in (
            "CUDA Preview Validation Gate",
            "CPU installer remains required and official",
            ".venv-cuda",
            "requirements-windows-cuda-experimental.txt",
            "scripts\\verify_dependency_imports.py",
            "build_windows_cuda_preview.ps1 -PythonExe",
            "dist\\ColorComicCudaPreview\\ColorComicCudaPreview.exe",
            "ISCC.exe packaging\\inno\\ColorComicCudaPreview.iss",
            "ColorComic-Setup-0.6.0-win64-cuda-preview.exe",
            "NVIDIA CUDA machine",
            "non-CUDA machine",
            "model weights are excluded",
            "Record artifact sizes",
            "must not ship unless every CUDA preview check",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, validation)

        for expected in (
            "CUDA preview release gate",
            "CPU installer remains required and official",
            "CUDA preview artifact is optional",
            "Do not ship `ColorComic-Setup-0.6.0-win64-cuda-preview.exe`",
            "recording all pass",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, plan)

    def test_cuda_preview_preferences_ui_boundary_is_documented(self):
        plan = self.read_file("packaging", "CUDA_BUILD_PLAN.md")

        for expected in (
            "Preferences And UI Boundary Audit",
            "Preferences storage defaults `default_device` to `cpu`",
            "preferences API accepts only `default_device: \"cpu\"`",
            "Preferences panel shows `Device: CPU only`",
            "per-job Detect GPU path with a hidden CUDA radio",
            "visible CUDA control on the CUDA preview runtime switch",
            "Do not expose CUDA as a saved preference",
            "keep CUDA source/env-only",
            "remain CPU-only/read-only",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, plan)

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
