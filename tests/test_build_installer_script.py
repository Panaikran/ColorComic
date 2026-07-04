import os
import unittest


class BuildInstallerScriptTests(unittest.TestCase):
    def read_script(self):
        root = os.getcwd()
        with open(os.path.join(root, "packaging", "build_installer.ps1"), encoding="utf-8") as handle:
            return handle.read()

    def test_inno_compiler_lookup_order_is_explicit_path_then_common_locations(self):
        script = self.read_script()

        markers = [
            'Add-InnoCandidate "Explicit -InnoCompiler" $InnoCompiler',
            "Get-Command ISCC.exe",
            'Add-InnoCandidate "LOCALAPPDATA"',
            'Add-InnoCandidate "ProgramFiles"',
            'Add-InnoCandidate "ProgramFiles(x86)"',
        ]
        positions = [script.index(marker) for marker in markers]

        self.assertEqual(positions, sorted(positions))

    def test_inno_compiler_lookup_tracks_all_checked_locations(self):
        script = self.read_script()

        self.assertIn("$CheckedInnoLocations", script)
        self.assertIn("PATH: ISCC.exe <not found>", script)
        self.assertIn("Checked locations:", script)
        self.assertIn("Install Inno Setup 6", script)
        self.assertIn("-InnoCompiler", script)

    def test_inno_compiler_paths_with_spaces_use_literal_path_and_call_operator(self):
        script = self.read_script()

        self.assertIn("Test-Path -LiteralPath $candidate.Path", script)
        self.assertIn("Resolve-Path -LiteralPath $candidate.Path", script)
        self.assertIn("& $ResolvedInnoCompiler $ScriptPath", script)

    def test_slice_does_not_bump_installer_version(self):
        script = self.read_script()

        self.assertIn("ColorComic-Setup-0.2.0-win64-cpu.exe", script)
        self.assertNotIn("ColorComic-Setup-0.2.1-win64-cpu.exe", script)


if __name__ == "__main__":
    unittest.main()
