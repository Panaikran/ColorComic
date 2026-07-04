import os
import unittest


class BuildWindowsScriptTests(unittest.TestCase):
    def read_script(self):
        root = os.getcwd()
        with open(os.path.join(root, "packaging", "build_windows.ps1"), encoding="utf-8") as handle:
            return handle.read()

    def test_prefers_repo_virtual_environment_python(self):
        script = self.read_script()

        self.assertIn('$VenvPython = Join-Path $RepoRoot ".venv\\Scripts\\python.exe"', script)
        self.assertIn("Test-Path -LiteralPath $VenvPython -PathType Leaf", script)
        self.assertIn("Resolve-Path -LiteralPath $VenvPython", script)
        self.assertIn('Write-Host "Using Python: $PythonExe"', script)

    def test_falls_back_to_path_python_with_clear_warning(self):
        script = self.read_script()

        self.assertIn("Falling back to python on PATH", script)
        self.assertIn("Get-Command python -ErrorAction SilentlyContinue", script)
        self.assertIn("Python was not found", script)

    def test_dependency_verification_uses_selected_python(self):
        script = self.read_script()

        self.assertIn("& $PythonExe scripts\\verify_dependency_imports.py", script)
        self.assertNotIn("python scripts\\verify_dependency_imports.py", script)

    def test_pyinstaller_runs_as_module_with_selected_python(self):
        script = self.read_script()

        self.assertIn("& $PythonExe -m PyInstaller packaging\\ColorComic.spec --clean --noconfirm", script)
        self.assertNotIn("pyinstaller packaging\\ColorComic.spec --clean --noconfirm", script)


if __name__ == "__main__":
    unittest.main()
