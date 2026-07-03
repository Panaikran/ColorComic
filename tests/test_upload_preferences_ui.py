import os
import unittest


class UploadPreferencesUiTests(unittest.TestCase):
    def test_upload_script_loads_preferences_without_saving_changes(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("fetch('/api/preferences')", script)
        self.assertIn("loadPreferences();", script)
        self.assertIn("applyModePreference(preferences.default_mode)", script)
        self.assertIn("applyDevicePreference(preferences.default_device)", script)
        self.assertNotIn("fetch('/api/preferences',", script)

    def test_upload_script_applies_existing_mode_selector_and_cpu_device_only(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("defaultMode !== 'auto' && defaultMode !== 'reference'", script)
        self.assertIn('input[name="mode"][value="${defaultMode}"]', script)
        self.assertIn("defaultDevice !== 'cpu'", script)
        self.assertIn('input[name="device"][value="cpu"]', script)
        self.assertNotIn("defaultDevice === 'cuda'", script)

    def test_upload_script_keeps_defaults_when_preferences_fetch_fails(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("catch (error)", script)
        self.assertIn("Keep the built-in form defaults when preferences are unavailable.", script)


if __name__ == "__main__":
    unittest.main()
