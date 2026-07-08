import importlib
import os
import shutil
import sys
import types
import unittest


class FakeConfig(dict):
    def from_object(self, obj):
        self["from_object"] = obj


class FakeFlask:
    last_instance = None

    def __init__(self, name):
        self.name = name
        self.config = FakeConfig()
        self.secret_key = None
        self.routes = {}
        self.run_calls = []
        FakeFlask.last_instance = self

    def route(self, rule, **options):
        def decorator(func):
            self.routes[rule] = func
            return func

        return decorator

    def run(self, **kwargs):
        self.run_calls.append(kwargs)


def install_fake_flask():
    fake_flask = types.ModuleType("flask")
    fake_flask.Flask = FakeFlask
    fake_flask.Response = lambda *args, **kwargs: ("response", args, kwargs)
    fake_flask.jsonify = lambda payload=None, **kwargs: payload if payload is not None else kwargs
    fake_flask.redirect = lambda target: ("redirect", target)
    fake_flask.render_template = lambda template, **kwargs: ("template", template, kwargs)
    fake_flask.request = types.SimpleNamespace(files={}, form={})
    fake_flask.send_file = lambda *args, **kwargs: ("send_file", args, kwargs)
    fake_flask.url_for = lambda endpoint: f"/{endpoint}"
    sys.modules["flask"] = fake_flask

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *args, **kwargs: True
    sys.modules["dotenv"] = fake_dotenv


class AppStartupTests(unittest.TestCase):
    def setUp(self):
        self.original_local_app_data = os.environ.get("LOCALAPPDATA")
        self.local_app_data = os.path.join(os.getcwd(), "tests")
        self.app_data = os.path.join(self.local_app_data, "ColorComic")
        shutil.rmtree(self.app_data, ignore_errors=True)
        os.environ["LOCALAPPDATA"] = self.local_app_data

    def tearDown(self):
        for name in (
            "app",
            "config",
            "core.paths",
            "flask",
            "dotenv",
            "torch",
            "cv2",
            "diffusers",
            "transformers",
            "core.model_manager",
            "core.model_downloader",
        ):
            sys.modules.pop(name, None)
        if self.original_local_app_data is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self.original_local_app_data
        shutil.rmtree(self.app_data, ignore_errors=True)

    def test_importing_app_has_no_model_side_effects(self):
        for name in (
            "app",
            "torch",
            "cv2",
            "diffusers",
            "transformers",
            "core.model_manager",
            "core.model_downloader",
        ):
            sys.modules.pop(name, None)

        imported = importlib.import_module("app")

        self.assertTrue(hasattr(imported, "create_app"))
        self.assertNotIn("core.model_downloader", sys.modules)
        self.assertNotIn("core.model_manager", sys.modules)
        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("cv2", sys.modules)
        self.assertNotIn("diffusers", sys.modules)
        self.assertNotIn("transformers", sys.modules)

    def test_create_app_returns_flask_app_and_health_responds(self):
        install_fake_flask()
        imported = importlib.import_module("app")

        flask_app = imported.create_app()

        self.assertIsInstance(flask_app, FakeFlask)
        self.assertIn("/api/health", flask_app.routes)
        self.assertEqual(flask_app.routes["/api/health"](), {"ok": True, "service": "ColorComic"})
        self.assertIn("/api/status", flask_app.routes)
        self.assertEqual(flask_app.routes["/api/status"]()["model_loaded"], False)

    def test_diagnostics_reports_runtime_status_without_initializing_model_manager(self):
        install_fake_flask()
        fake_torch = types.ModuleType("torch")
        fake_torch.cuda = types.SimpleNamespace(is_available=lambda: False)
        sys.modules["torch"] = fake_torch
        imported = importlib.import_module("app")
        imported._model_manager = None

        flask_app = imported.create_app()
        payload = flask_app.routes["/api/diagnostics"]()

        self.assertFalse(payload["model_manager"]["initialized"])
        self.assertIsNone(imported._model_manager)
        self.assertIn("runtime", payload["paths"])
        self.assertIn("uploads", payload["paths"])
        self.assertIn("output", payload["paths"])
        self.assertIn("models", payload["paths"])
        self.assertIn("cache", payload["paths"])
        self.assertIn("logs", payload["paths"])
        self.assertIn("config", payload["paths"])
        self.assertIn("cwd", payload["process"])
        self.assertIn("version", payload["python"])
        self.assertIn("free_bytes", payload["disk"]["runtime"])
        self.assertFalse(payload["device"]["cuda_available"])

    def test_create_app_registers_favicon_route(self):
        install_fake_flask()
        imported = importlib.import_module("app")

        flask_app = imported.create_app()

        self.assertIn("/favicon.ico", flask_app.routes)
        self.assertEqual(
            flask_app.routes["/favicon.ico"](),
            (
                "send_file",
                (imported.Config.APP_ICON_PATH,),
                {"mimetype": "image/x-icon"},
            ),
        )

    def test_run_dev_server_remains_available(self):
        install_fake_flask()
        imported = importlib.import_module("app")

        imported.run_dev_server()

        self.assertEqual(FakeFlask.last_instance.run_calls, [
            {"debug": True, "port": 5000, "threaded": True, "use_reloader": False}
        ])
