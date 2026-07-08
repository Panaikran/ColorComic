import importlib
import json
import os
import sys
import tempfile
import types
import unittest

from core.preferences import DEFAULT_PREFERENCES, load_preferences, save_preferences


class FakeConfig(dict):
    def from_object(self, obj):
        self["from_object"] = obj


class FakeFlask:
    def __init__(self, name):
        self.name = name
        self.config = FakeConfig()
        self.routes = {}

    def route(self, rule, **options):
        def decorator(func):
            self.routes[rule] = func
            return func

        return decorator


class FakeRequest:
    method = "GET"
    files = {}
    form = {}
    _json_payload = None

    def get_json(self, silent=False):
        return self._json_payload


def install_fake_flask():
    fake_flask = types.ModuleType("flask")
    fake_flask.Flask = FakeFlask
    fake_flask.Response = lambda *args, **kwargs: ("response", args, kwargs)
    fake_flask.jsonify = lambda payload=None, **kwargs: payload if payload is not None else kwargs
    fake_flask.redirect = lambda target: ("redirect", target)
    fake_flask.render_template = lambda template, **kwargs: ("template", template, kwargs)
    fake_flask.request = FakeRequest()
    fake_flask.send_file = lambda *args, **kwargs: ("send_file", args, kwargs)
    fake_flask.url_for = lambda endpoint: f"/{endpoint}"
    sys.modules["flask"] = fake_flask

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *args, **kwargs: True
    sys.modules["dotenv"] = fake_dotenv
    return fake_flask


class PreferencesApiTests(unittest.TestCase):
    def setUp(self):
        for name in ("app", "flask", "dotenv"):
            sys.modules.pop(name, None)
        self.fake_flask = install_fake_flask()
        self.app_module = importlib.import_module("app")
        self.flask_app = self.app_module.create_app()

    def tearDown(self):
        self.app_module.jobs.clear()
        self.app_module.job_queues.clear()
        for name in ("app", "flask", "dotenv"):
            sys.modules.pop(name, None)

    def call_preferences(self, method="GET", payload=None):
        self.fake_flask.request.method = method
        self.fake_flask.request._json_payload = payload
        return self.flask_app.routes["/api/preferences"]()

    def call_preferences_reset(self):
        self.fake_flask.request.method = "POST"
        return self.flask_app.routes["/api/preferences/reset"]()

    def test_get_preferences_returns_defaults_when_file_is_missing(self):
        original_config_dir = self.app_module.Config.CONFIG_DIR

        with tempfile.TemporaryDirectory() as temp_dir:
            self.app_module.Config.CONFIG_DIR = temp_dir
            try:
                payload = self.call_preferences()
            finally:
                self.app_module.Config.CONFIG_DIR = original_config_dir

        self.assertEqual(payload, {"preferences": DEFAULT_PREFERENCES})

    def test_get_preferences_recovers_from_corrupt_file(self):
        original_config_dir = self.app_module.Config.CONFIG_DIR

        with tempfile.TemporaryDirectory() as temp_dir:
            os.makedirs(temp_dir, exist_ok=True)
            with open(os.path.join(temp_dir, "preferences.json"), "w", encoding="utf-8") as handle:
                handle.write("{bad json")
            self.app_module.Config.CONFIG_DIR = temp_dir

            try:
                payload = self.call_preferences()
            finally:
                self.app_module.Config.CONFIG_DIR = original_config_dir

        self.assertEqual(payload, {"preferences": DEFAULT_PREFERENCES})

    def test_post_preferences_saves_valid_partial_update(self):
        original_config_dir = self.app_module.Config.CONFIG_DIR

        with tempfile.TemporaryDirectory() as temp_dir:
            existing = dict(DEFAULT_PREFERENCES)
            existing["default_mode"] = "reference"
            save_preferences(existing, os.path.join(temp_dir, "preferences.json"))
            self.app_module.Config.CONFIG_DIR = temp_dir

            try:
                payload = self.call_preferences(
                    "POST",
                    {"open_output_folder_after_completion": True},
                )
                saved = load_preferences(os.path.join(temp_dir, "preferences.json"))
            finally:
                self.app_module.Config.CONFIG_DIR = original_config_dir

        expected = dict(DEFAULT_PREFERENCES)
        expected["default_mode"] = "reference"
        expected["open_output_folder_after_completion"] = True
        self.assertEqual(payload, {"preferences": expected})
        self.assertEqual(saved, expected)

    def test_post_preferences_accepts_reference_mode_and_cpu_device(self):
        original_config_dir = self.app_module.Config.CONFIG_DIR

        with tempfile.TemporaryDirectory() as temp_dir:
            self.app_module.Config.CONFIG_DIR = temp_dir
            try:
                payload = self.call_preferences(
                    "POST",
                    {"default_mode": "reference", "default_device": "cpu"},
                )
            finally:
                self.app_module.Config.CONFIG_DIR = original_config_dir

        expected = dict(DEFAULT_PREFERENCES)
        expected["default_mode"] = "reference"
        expected["default_device"] = "cpu"
        self.assertEqual(payload, {"preferences": expected})

    def test_post_preferences_rejects_invalid_values(self):
        cases = [
            ({"default_mode": "manual"}, "default_mode must be auto or reference."),
            ({"default_device": "auto"}, "default_device must be cpu."),
            ({"open_output_folder_after_completion": "yes"}, "must be true or false."),
            (["not", "an", "object"], "Preferences payload must be a JSON object."),
        ]

        original_config_dir = self.app_module.Config.CONFIG_DIR
        with tempfile.TemporaryDirectory() as temp_dir:
            self.app_module.Config.CONFIG_DIR = temp_dir
            try:
                for update, expected_error in cases:
                    with self.subTest(update=update):
                        response, status = self.call_preferences("POST", update)
                        self.assertEqual(status, 400)
                        self.assertIn(expected_error, response["error"])
                        self.assertEqual(response["preferences"], DEFAULT_PREFERENCES)
            finally:
                self.app_module.Config.CONFIG_DIR = original_config_dir

    def test_post_preferences_reset_saves_defaults(self):
        original_config_dir = self.app_module.Config.CONFIG_DIR

        with tempfile.TemporaryDirectory() as temp_dir:
            save_preferences(
                {
                    "default_mode": "reference",
                    "open_output_folder_after_completion": True,
                },
                os.path.join(temp_dir, "preferences.json"),
            )
            self.app_module.Config.CONFIG_DIR = temp_dir
            try:
                payload = self.call_preferences_reset()
                saved = load_preferences(os.path.join(temp_dir, "preferences.json"))
            finally:
                self.app_module.Config.CONFIG_DIR = original_config_dir

        self.assertEqual(payload, {"preferences": DEFAULT_PREFERENCES})
        self.assertEqual(saved, DEFAULT_PREFERENCES)

    def test_post_preferences_reset_recovers_from_corrupt_file(self):
        original_config_dir = self.app_module.Config.CONFIG_DIR

        with tempfile.TemporaryDirectory() as temp_dir:
            with open(os.path.join(temp_dir, "preferences.json"), "w", encoding="utf-8") as handle:
                handle.write("{bad json")
            self.app_module.Config.CONFIG_DIR = temp_dir
            try:
                payload = self.call_preferences_reset()
                saved = load_preferences(os.path.join(temp_dir, "preferences.json"))
            finally:
                self.app_module.Config.CONFIG_DIR = original_config_dir

        self.assertEqual(payload, {"preferences": DEFAULT_PREFERENCES})
        self.assertEqual(saved, DEFAULT_PREFERENCES)


if __name__ == "__main__":
    unittest.main()
