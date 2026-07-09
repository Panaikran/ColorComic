import importlib
import os
import shutil
import sys
import types
import unittest


_MISSING = object()
_IMPORT_SENSITIVE_MODULES = ("torch", "cv2", "diffusers", "transformers")


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
        self.original_import_modules = {
            name: sys.modules.get(name, _MISSING)
            for name in _IMPORT_SENSITIVE_MODULES
        }
        self.original_local_app_data = os.environ.get("LOCALAPPDATA")
        self.original_cuda_preview = os.environ.get("COLORCOMIC_CUDA_PREVIEW")
        self.local_app_data = os.path.join(os.getcwd(), "tests")
        self.app_data = os.path.join(self.local_app_data, "ColorComic")
        shutil.rmtree(self.app_data, ignore_errors=True)
        os.environ["LOCALAPPDATA"] = self.local_app_data
        os.environ.pop("COLORCOMIC_CUDA_PREVIEW", None)

    def tearDown(self):
        for name in (
            "app",
            "config",
            "core.paths",
            "flask",
            "dotenv",
            "core.model_manager",
            "core.model_downloader",
        ):
            sys.modules.pop(name, None)
        for name, module in self.original_import_modules.items():
            if module is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        if self.original_local_app_data is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self.original_local_app_data
        if self.original_cuda_preview is None:
            os.environ.pop("COLORCOMIC_CUDA_PREVIEW", None)
        else:
            os.environ["COLORCOMIC_CUDA_PREVIEW"] = self.original_cuda_preview
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
        fake_torch = types.ModuleType("torch")
        fake_torch.cuda = types.SimpleNamespace(is_available=lambda: False)
        sys.modules["torch"] = fake_torch
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
        self.assertFalse(payload["device"]["cuda_preview_enabled"])
        self.assertEqual(payload["device"]["requested_device"], "auto")
        self.assertEqual(payload["device"]["resolved_device"], "cpu")
        self.assertEqual(payload["device"]["current"], "cpu")
        self.assertEqual(payload["device"]["capabilities"]["current_default_device"], "cpu")
        self.assertNotIn("fallback_reason", payload["device"])
        self.assertNotIn("core.model_manager", sys.modules)

    def test_diagnostics_reports_cuda_preview_capabilities_without_initializing_models(self):
        install_fake_flask()
        os.environ["COLORCOMIC_CUDA_PREVIEW"] = "1"
        fake_torch = types.ModuleType("torch")
        fake_torch.__version__ = "2.5.1+cu121"
        fake_torch.version = types.SimpleNamespace(cuda="12.1")
        fake_torch.cuda = types.SimpleNamespace(
            is_available=lambda: True,
            device_count=lambda: 1,
            get_device_properties=lambda index: types.SimpleNamespace(
                name="NVIDIA Test GPU",
                total_memory=8 * 1024**3,
            ),
        )
        sys.modules["torch"] = fake_torch
        imported = importlib.import_module("app")
        imported._model_manager = None

        flask_app = imported.create_app()
        payload = flask_app.routes["/api/diagnostics"]()

        self.assertTrue(payload["device"]["cuda_preview_enabled"])
        self.assertTrue(payload["device"]["cuda_available"])
        self.assertEqual(payload["device"]["requested_device"], "auto")
        self.assertEqual(payload["device"]["resolved_device"], "cpu")
        self.assertEqual(payload["device"]["capabilities"]["cuda_version"], "12.1")
        self.assertEqual(payload["device"]["capabilities"]["gpus"][0]["name"], "NVIDIA Test GPU")
        self.assertIsNone(imported._model_manager)
        self.assertNotIn("core.model_manager", sys.modules)

    def test_diagnostics_includes_loaded_model_device_and_fallback_reason_when_available(self):
        install_fake_flask()
        fake_torch = types.ModuleType("torch")
        fake_torch.cuda = types.SimpleNamespace(is_available=lambda: False)
        sys.modules["torch"] = fake_torch
        imported = importlib.import_module("app")
        imported._model_manager = types.SimpleNamespace(
            device_name="cpu",
            _colorizer=types.SimpleNamespace(fallback_reason="cuda_out_of_memory"),
        )

        flask_app = imported.create_app()
        payload = flask_app.routes["/api/diagnostics"]()

        self.assertEqual(payload["device"]["loaded_model_device"], "cpu")
        self.assertEqual(payload["device"]["fallback_reason"], "cuda_out_of_memory")

    def test_diagnostics_bundle_route_does_not_initialize_model_manager(self):
        install_fake_flask()
        fake_torch = types.ModuleType("torch")
        fake_torch.cuda = types.SimpleNamespace(is_available=lambda: False)
        sys.modules["torch"] = fake_torch
        imported = importlib.import_module("app")
        imported._model_manager = None

        flask_app = imported.create_app()
        response = flask_app.routes["/api/diagnostics/bundle"]()

        self.assertIsNone(imported._model_manager)
        self.assertEqual(response[0], "send_file")
        self.assertEqual(response[2]["mimetype"], "application/zip")
        self.assertTrue(response[2]["as_attachment"])
        self.assertTrue(response[2]["download_name"].startswith("ColorComic-diagnostics-"))

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
