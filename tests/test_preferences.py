import json
import os
import tempfile
import unittest
from unittest import mock

from core.preferences import (
    DEFAULT_PREFERENCES,
    PREFERENCES_FILENAME,
    get_preferences_path,
    load_preferences,
    reset_preferences,
    save_preferences,
)


class PreferencesTests(unittest.TestCase):
    def test_preferences_path_uses_config_dir(self):
        self.assertEqual(
            get_preferences_path(r"C:\Runtime\Config"),
            os.path.join(r"C:\Runtime\Config", PREFERENCES_FILENAME),
        )

    def test_missing_preferences_file_loads_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            preferences = load_preferences(os.path.join(temp_dir, PREFERENCES_FILENAME))

        self.assertEqual(preferences, DEFAULT_PREFERENCES)

    def test_corrupt_preferences_file_loads_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, PREFERENCES_FILENAME)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{not valid json")

            preferences = load_preferences(path)

        self.assertEqual(preferences, DEFAULT_PREFERENCES)

    def test_partial_preferences_merge_with_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, PREFERENCES_FILENAME)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"default_mode": "reference"}, handle)

            preferences = load_preferences(path)

        expected = dict(DEFAULT_PREFERENCES)
        expected["default_mode"] = "reference"
        self.assertEqual(preferences, expected)

    def test_invalid_preference_values_fall_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, PREFERENCES_FILENAME)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "default_mode": "surprise",
                        "default_device": "cuda",
                        "open_output_folder_after_completion": "yes",
                    },
                    handle,
                )

            preferences = load_preferences(path)

        self.assertEqual(preferences, DEFAULT_PREFERENCES)

    def test_save_preferences_uses_atomic_replace_and_round_trips(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "nested", PREFERENCES_FILENAME)
            preferences = dict(DEFAULT_PREFERENCES)
            preferences["default_mode"] = "reference"

            with mock.patch("core.preferences.os.replace", wraps=os.replace) as replace:
                saved = save_preferences(preferences, path)
            loaded = load_preferences(path)

        self.assertEqual(saved, preferences)
        self.assertEqual(loaded, preferences)
        replace.assert_called_once()
        self.assertNotEqual(replace.call_args.args[0], path)
        self.assertEqual(replace.call_args.args[1], path)

    def test_reset_preferences_saves_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, PREFERENCES_FILENAME)
            save_preferences({"default_mode": "reference"}, path)

            reset = reset_preferences(path)
            loaded = load_preferences(path)

        self.assertEqual(reset, DEFAULT_PREFERENCES)
        self.assertEqual(loaded, DEFAULT_PREFERENCES)


if __name__ == "__main__":
    unittest.main()
