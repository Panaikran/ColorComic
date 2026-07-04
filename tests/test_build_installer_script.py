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

    def test_installer_preflight_checks_required_build_inputs(self):
        script = self.read_script()

        self.assertIn('$DistDir = Join-Path $RepoRoot "dist\\ColorComic"', script)
        self.assertIn('$DistExe = Join-Path $DistDir "ColorComic.exe"', script)
        self.assertIn('$InnoDir = Join-Path $RepoRoot "packaging\\inno"', script)
        self.assertIn('$ScriptPath = Join-Path $InnoDir "ColorComic.iss"', script)
        self.assertIn("function Assert-InstallerBuildInputs", script)
        self.assertIn("Test-Path -LiteralPath $ScriptPath -PathType Leaf", script)
        self.assertIn("Test-Path -LiteralPath $DistDir -PathType Container", script)
        self.assertIn("Test-Path -LiteralPath $DistExe -PathType Leaf", script)
        self.assertIn('Join-Path $DistDir "_internal"', script)
        self.assertIn("PyInstaller one-folder support directory not found", script)

    def test_installer_preflight_guidance_runs_before_inno_invocation(self):
        script = self.read_script()

        self.assertIn("Installer build preflight failed.", script)
        self.assertIn(".\\packaging\\build_windows.ps1", script)
        preflight_call = script.rindex("Assert-InstallerBuildInputs")
        self.assertLess(preflight_call, script.index("Get-Command ISCC.exe"))
        self.assertLess(preflight_call, script.index("& $ResolvedInnoCompiler $ScriptPath"))

    def test_installer_output_validation_checks_file_and_size(self):
        script = self.read_script()

        self.assertIn('$InstallerFileName = "ColorComic-Setup-0.2.0-win64-cpu.exe"', script)
        self.assertIn('$InstallerOutputPath = Join-Path (Join-Path $InnoDir "output") $InstallerFileName', script)
        self.assertIn("function Assert-InstallerOutput", script)
        self.assertIn("Test-Path -LiteralPath $InstallerOutputPath -PathType Leaf", script)
        self.assertIn("Get-Item -LiteralPath $InstallerOutputPath", script)
        self.assertIn("$installer.Length -le 0", script)
        self.assertIn("Installer validation failed", script)

    def test_installer_output_validation_reports_artifact_details_after_compile(self):
        script = self.read_script()

        self.assertIn("Installer filename: $InstallerFileName", script)
        self.assertIn("Installer path: $($installer.FullName)", script)
        self.assertIn("Installer size: $sizeMb MB", script)
        self.assertLess(script.index("& $ResolvedInnoCompiler $ScriptPath"), script.rindex("Assert-InstallerOutput"))

    def test_slice_does_not_bump_installer_version(self):
        script = self.read_script()

        self.assertIn("ColorComic-Setup-0.2.0-win64-cpu.exe", script)
        self.assertNotIn("ColorComic-Setup-0.2.1-win64-cpu.exe", script)


if __name__ == "__main__":
    unittest.main()
