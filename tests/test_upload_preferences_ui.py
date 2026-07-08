import os
import unittest


class UploadPreferencesUiTests(unittest.TestCase):
    def test_upload_page_contains_preferences_section(self):
        root = os.getcwd()
        with open(os.path.join(root, "templates", "index.html"), encoding="utf-8") as handle:
            template = handle.read()

        self.assertIn('id="preferencesSection"', template)
        self.assertIn('id="savePreferencesBtn"', template)
        self.assertIn('id="resetPreferencesBtn"', template)
        self.assertIn("Reset to Defaults", template)
        self.assertIn('name="prefDefaultMode"', template)
        self.assertIn('id="prefOpenOutputFolder"', template)
        self.assertIn('id="preferencesStatus" role="status" aria-live="polite"', template)
        self.assertIn("Device: CPU only", template)
        self.assertNotIn('name="prefDefaultDevice"', template)
        self.assertNotIn('value="cuda"', template.split('id="preferencesSection"', 1)[1].split('id="uploadBtn"', 1)[0])

    def test_upload_script_loads_preferences_and_populates_settings(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("fetch('/api/preferences')", script)
        self.assertIn("loadPreferences();", script)
        self.assertIn("applyPreferences(preferences)", script)
        self.assertIn("applyOutputFolderPreference(preferences.open_output_folder_after_completion)", script)
        self.assertIn('input[name="prefDefaultMode"][value="${defaultMode}"]', script)

    def test_upload_script_applies_existing_mode_selector_and_cpu_device_only(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("defaultMode !== 'auto' && defaultMode !== 'reference'", script)
        self.assertIn('input[name="mode"][value="${defaultMode}"]', script)
        self.assertIn("defaultDevice !== 'cpu'", script)
        self.assertIn('input[name="device"][value="cpu"]', script)
        self.assertNotIn("defaultDevice === 'cuda'", script)

    def test_upload_script_saves_preferences_with_explicit_button(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("savePreferencesBtn.addEventListener('click', savePreferences)", script)
        self.assertIn("fetch('/api/preferences',", script)
        self.assertIn("method: 'POST'", script)
        self.assertIn("default_mode: getSelectedPreferenceMode()", script)
        self.assertIn("default_device: 'cpu'", script)
        self.assertIn("open_output_folder_after_completion", script)
        self.assertIn("Preferences saved.", script)
        self.assertIn("Could not save preferences.", script)

    def test_upload_script_resets_preferences_with_explicit_button(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("const resetPreferencesBtn = document.getElementById('resetPreferencesBtn')", script)
        self.assertIn("resetPreferencesBtn.addEventListener('click', resetPreferences)", script)
        self.assertIn("fetch('/api/preferences/reset', { method: 'POST' })", script)
        self.assertIn("applyPreferences(preferences)", script)
        self.assertIn("Preferences reset to defaults.", script)
        self.assertIn("Could not reset preferences.", script)

    def test_upload_script_keeps_defaults_when_preferences_fetch_fails(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("catch (error)", script)
        self.assertIn("Keep the built-in form defaults when preferences are unavailable.", script)


if __name__ == "__main__":
    unittest.main()
