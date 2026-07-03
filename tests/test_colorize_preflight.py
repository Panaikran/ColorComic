import importlib
import json
import os
import sys
import tempfile
import types
import unittest


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


class FakeThread:
    instances = []

    def __init__(self, target, daemon=False):
        self.target = target
        self.daemon = daemon
        self.started = False
        FakeThread.instances.append(self)

    def start(self):
        self.started = True


class ColorizePreflightRouteTests(unittest.TestCase):
    def setUp(self):
        self.modules_to_clear = ("app", "flask", "dotenv")
        for name in self.modules_to_clear:
            sys.modules.pop(name, None)
        install_fake_flask()
        self.app_module = importlib.import_module("app")
        self.flask_app = self.app_module.create_app()

    def tearDown(self):
        self.app_module.jobs.clear()
        self.app_module.job_queues.clear()
        for name in self.modules_to_clear:
            sys.modules.pop(name, None)

    def test_preflight_failure_streams_existing_error_shape_before_model_load(self):
        app = self.app_module
        model_load_called = {"value": False}

        def fail_if_model_loads():
            model_load_called["value"] = True
            raise AssertionError("model manager should not be created")

        original_get_model_manager = app.get_model_manager
        original_output_folder = app.Config.OUTPUT_FOLDER

        with tempfile.TemporaryDirectory() as temp_dir:
            app.Config.OUTPUT_FOLDER = os.path.join(temp_dir, "output")
            job_id = "preflight-fail"
            app.jobs[job_id] = types.SimpleNamespace(
                job_id=job_id,
                pdf_path=os.path.join(temp_dir, "missing.pdf"),
                status="uploaded",
                progress=0.0,
                current_step="",
                mode="auto",
                output_pdf=None,
            )
            app.get_model_manager = fail_if_model_loads

            try:
                response = self.flask_app.routes["/api/colorize/<job_id>"](job_id)
                stream_response = self.flask_app.routes["/api/colorize/<job_id>/stream"](job_id)
                generator = stream_response[1][0]
                payload = json.loads(next(generator).removeprefix("data: ").strip())
            finally:
                app.get_model_manager = original_get_model_manager
                app.Config.OUTPUT_FOLDER = original_output_folder

        self.assertEqual(response, {"ok": True})
        self.assertFalse(model_load_called["value"])
        self.assertEqual(app.jobs[job_id].status, "error")
        self.assertEqual(payload["done"], True)
        self.assertEqual(payload["step"], "PDF preflight")
        self.assertEqual(
            payload["error"],
            "Choose the PDF again. ColorComic could not find the uploaded file.",
        )

    def test_successful_preflight_still_schedules_colorization_thread(self):
        app = self.app_module
        original_thread = app.threading.Thread
        original_output_folder = app.Config.OUTPUT_FOLDER
        original_preflight = app.validate_colorize_preflight
        FakeThread.instances = []

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = os.path.join(temp_dir, "input.pdf")
            with open(pdf_path, "wb") as handle:
                handle.write(b"%PDF-1.4\n")

            app.Config.OUTPUT_FOLDER = os.path.join(temp_dir, "output")
            job_id = "preflight-pass"
            app.jobs[job_id] = types.SimpleNamespace(
                job_id=job_id,
                pdf_path=pdf_path,
                page_count=1,
                page_images=[],
                colorized_images=[],
                status="uploaded",
                progress=0.0,
                current_step="",
                style="auto",
                device="auto",
                mode="auto",
                reference_image_path=None,
                output_pdf=None,
            )
            app.threading.Thread = FakeThread
            app.validate_colorize_preflight = (
                lambda pdf_path, job_id, output_folder, **kwargs: types.SimpleNamespace(
                    ok=True,
                    output_dir=os.path.join(output_folder, job_id),
                    errors=(),
                )
            )

            try:
                response = self.flask_app.routes["/api/colorize/<job_id>"](job_id)
            finally:
                app.threading.Thread = original_thread
                app.Config.OUTPUT_FOLDER = original_output_folder
                app.validate_colorize_preflight = original_preflight

        self.assertEqual(response, {"ok": True})
        self.assertEqual(app.jobs[job_id].status, "colorizing")
        self.assertTrue(FakeThread.instances)
        self.assertTrue(FakeThread.instances[0].started)

    def test_reference_preflight_failure_stops_before_model_load(self):
        app = self.app_module
        model_load_called = {"value": False}

        def fail_if_model_loads():
            model_load_called["value"] = True
            raise AssertionError("model manager should not be created")

        original_get_model_manager = app.get_model_manager
        original_output_folder = app.Config.OUTPUT_FOLDER
        original_preflight = app.validate_colorize_preflight

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = os.path.join(temp_dir, "input.pdf")
            with open(pdf_path, "wb") as handle:
                handle.write(b"%PDF-1.4\n")

            app.Config.OUTPUT_FOLDER = os.path.join(temp_dir, "output")
            job_id = "reference-preflight-fail"
            app.jobs[job_id] = types.SimpleNamespace(
                job_id=job_id,
                pdf_path=pdf_path,
                page_count=1,
                page_images=[],
                colorized_images=[],
                status="uploaded",
                progress=0.0,
                current_step="",
                style="auto",
                device="auto",
                mode="reference",
                reference_image_path=os.path.join(temp_dir, "missing-reference.png"),
                output_pdf=None,
            )
            app.get_model_manager = fail_if_model_loads

            def fail_reference_preflight(
                pdf_path,
                job_id,
                output_folder,
                mode,
                reference_image_path,
            ):
                return types.SimpleNamespace(
                    ok=False,
                    errors=(
                        types.SimpleNamespace(
                            code="reference_missing",
                            message="Choose the reference image again. ColorComic could not find it.",
                            step="reference preflight",
                        ),
                    ),
                    output_dir=os.path.join(output_folder, job_id),
                )

            app.validate_colorize_preflight = fail_reference_preflight

            try:
                response = self.flask_app.routes["/api/colorize/<job_id>"](job_id)
                stream_response = self.flask_app.routes["/api/colorize/<job_id>/stream"](job_id)
                generator = stream_response[1][0]
                payload = json.loads(next(generator).removeprefix("data: ").strip())
            finally:
                app.get_model_manager = original_get_model_manager
                app.Config.OUTPUT_FOLDER = original_output_folder
                app.validate_colorize_preflight = original_preflight

        self.assertEqual(response, {"ok": True})
        self.assertFalse(model_load_called["value"])
        self.assertEqual(app.jobs[job_id].status, "error")
        self.assertEqual(payload["done"], True)
        self.assertEqual(payload["step"], "reference preflight")
        self.assertEqual(
            payload["error"],
            "Choose the reference image again. ColorComic could not find it.",
        )


if __name__ == "__main__":
    unittest.main()
