import importlib
import json
import os
import sys
import tempfile
import types
import unittest

from core.preflight import PreflightError, PreflightResult


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

    def make_job(self, job_id, pdf_path):
        return types.SimpleNamespace(
            job_id=job_id,
            pdf_path=pdf_path,
            page_count=1,
            page_images=[],
            colorized_images=[],
            status="uploaded",
            progress=0.0,
            current_step="",
            style="auto",
            device="cpu",
            mode="auto",
            reference_image_path=None,
            output_pdf=None,
        )

    def successful_preflight(self, output_folder, job_id):
        return types.SimpleNamespace(
            ok=True,
            output_dir=os.path.join(output_folder, job_id),
            errors=(),
        )

    def test_duplicate_active_request_is_rejected_without_creating_another_worker(self):
        app = self.app_module
        original_thread = app.threading.Thread
        original_preflight = app.validate_colorize_preflight
        original_worker = app._run_colorization_job
        FakeThread.instances = []

        with tempfile.TemporaryDirectory() as temp_dir:
            job_id = "duplicate-start"
            app.jobs[job_id] = self.make_job(job_id, os.path.join(temp_dir, "input.pdf"))
            app.threading.Thread = FakeThread
            app.validate_colorize_preflight = (
                lambda pdf_path, job_id, output_folder, **kwargs: self.successful_preflight(output_folder, job_id)
            )
            app._run_colorization_job = lambda *args: True

            try:
                first_response = self.flask_app.routes["/api/colorize/<job_id>"](job_id)
                active_queue = app.job_queues[job_id]
                duplicate_response = self.flask_app.routes["/api/colorize/<job_id>"](job_id)
            finally:
                app.threading.Thread = original_thread
                app.validate_colorize_preflight = original_preflight
                app._run_colorization_job = original_worker

        self.assertEqual(first_response, {"ok": True})
        self.assertEqual(duplicate_response, ({"error": "Job is already running"}, 409))
        self.assertEqual(len(FakeThread.instances), 1)
        self.assertIs(app.job_queues[job_id], active_queue)

    def test_preflight_failure_allows_a_new_execution_attempt(self):
        app = self.app_module
        original_thread = app.threading.Thread
        original_preflight = app.validate_colorize_preflight
        original_worker = app._run_colorization_job
        FakeThread.instances = []

        with tempfile.TemporaryDirectory() as temp_dir:
            job_id = "preflight-retry"
            app.jobs[job_id] = self.make_job(job_id, os.path.join(temp_dir, "input.pdf"))
            results = iter((
                types.SimpleNamespace(
                    ok=False,
                    output_dir=os.path.join(temp_dir, "output", job_id),
                    errors=(types.SimpleNamespace(message="invalid PDF", step="PDF preflight"),),
                ),
                self.successful_preflight(os.path.join(temp_dir, "output"), job_id),
            ))
            app.threading.Thread = FakeThread
            app.validate_colorize_preflight = lambda *args, **kwargs: next(results)
            app._run_colorization_job = lambda *args: True

            try:
                failed_response = self.flask_app.routes["/api/colorize/<job_id>"](job_id)
                failed_queue = app.job_queues[job_id]
                retry_response = self.flask_app.routes["/api/colorize/<job_id>"](job_id)
            finally:
                app.threading.Thread = original_thread
                app.validate_colorize_preflight = original_preflight
                app._run_colorization_job = original_worker

        self.assertEqual(failed_response, {"ok": True})
        self.assertEqual(retry_response, {"ok": True})
        self.assertEqual(len(FakeThread.instances), 1)
        self.assertIsNot(app.job_queues[job_id], failed_queue)

    def test_terminal_completion_allows_a_new_execution_attempt(self):
        app = self.app_module
        original_thread = app.threading.Thread
        original_preflight = app.validate_colorize_preflight
        original_worker = app._run_colorization_job
        FakeThread.instances = []

        with tempfile.TemporaryDirectory() as temp_dir:
            job_id = "terminal-retry"
            job = self.make_job(job_id, os.path.join(temp_dir, "input.pdf"))
            app.jobs[job_id] = job
            app.threading.Thread = FakeThread
            app.validate_colorize_preflight = (
                lambda pdf_path, job_id, output_folder, **kwargs: self.successful_preflight(output_folder, job_id)
            )

            def complete_worker(*args):
                job.status = "completed"
                return True

            app._run_colorization_job = complete_worker

            try:
                first_response = self.flask_app.routes["/api/colorize/<job_id>"](job_id)
                FakeThread.instances[0].target()
                retry_response = self.flask_app.routes["/api/colorize/<job_id>"](job_id)
            finally:
                app.threading.Thread = original_thread
                app.validate_colorize_preflight = original_preflight
                app._run_colorization_job = original_worker

        self.assertEqual(first_response, {"ok": True})
        self.assertEqual(retry_response, {"ok": True})
        self.assertEqual(len(FakeThread.instances), 2)

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
        original_worker = app._run_colorization_job
        FakeThread.instances = []
        worker_call = {}

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = os.path.join(temp_dir, "input.pdf")
            with open(pdf_path, "wb") as handle:
                handle.write(b"%PDF-1.4\n")

            app.Config.OUTPUT_FOLDER = os.path.join(temp_dir, "output")
            job_id = "preflight-pass"
            expected_out_dir = os.path.join(app.Config.OUTPUT_FOLDER, job_id)
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

            def fake_worker(called_job_id, called_job, event_queue, out_dir):
                worker_call["job_id"] = called_job_id
                worker_call["job"] = called_job
                worker_call["event_queue"] = event_queue
                worker_call["out_dir"] = out_dir
                return True

            app._run_colorization_job = fake_worker

            try:
                response = self.flask_app.routes["/api/colorize/<job_id>"](job_id)
                scheduled_queue = app.job_queues[job_id]
                FakeThread.instances[0].target()
            finally:
                app.threading.Thread = original_thread
                app.Config.OUTPUT_FOLDER = original_output_folder
                app.validate_colorize_preflight = original_preflight
                app._run_colorization_job = original_worker

        self.assertEqual(response, {"ok": True})
        self.assertEqual(app.jobs[job_id].status, "colorizing")
        self.assertTrue(FakeThread.instances)
        self.assertTrue(FakeThread.instances[0].started)
        self.assertEqual(worker_call["job_id"], job_id)
        self.assertIs(worker_call["job"], app.jobs[job_id])
        self.assertIs(worker_call["event_queue"], scheduled_queue)
        self.assertEqual(worker_call["out_dir"], expected_out_dir)
        self.assertNotIn(job_id, app.job_queues)

    def test_runtime_health_failure_stops_before_model_load(self):
        app = self.app_module
        model_load_called = {"value": False}

        def fail_if_model_loads():
            model_load_called["value"] = True
            raise AssertionError("model manager should not be created")

        original_get_model_manager = app.get_model_manager
        original_preflight = app.validate_colorize_preflight
        original_runtime_health = app._runtime_health_errors

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = os.path.join(temp_dir, "input.pdf")
            with open(pdf_path, "wb") as handle:
                handle.write(b"%PDF-1.4\n")

            job_id = "runtime-health-fail"
            app.jobs[job_id] = types.SimpleNamespace(
                job_id=job_id,
                pdf_path=pdf_path,
                status="uploaded",
                progress=0.0,
                current_step="",
                mode="auto",
                output_pdf=None,
            )
            app.get_model_manager = fail_if_model_loads
            app.validate_colorize_preflight = lambda *args, **kwargs: PreflightResult(
                ok=True,
                pdf_path=pdf_path,
                output_dir=os.path.join(temp_dir, "output", job_id),
                page_count=1,
                reference_image_path=None,
                errors=(),
            )
            app._runtime_health_errors = lambda: (
                PreflightError(
                    code="runtime_disk_low",
                    message="ColorComic needs more free disk space before processing. Free some space and try again.",
                    step="runtime preflight",
                ),
            )

            try:
                response = self.flask_app.routes["/api/colorize/<job_id>"](job_id)
                stream_response = self.flask_app.routes["/api/colorize/<job_id>/stream"](job_id)
                generator = stream_response[1][0]
                payload = json.loads(next(generator).removeprefix("data: ").strip())
            finally:
                app.get_model_manager = original_get_model_manager
                app.validate_colorize_preflight = original_preflight
                app._runtime_health_errors = original_runtime_health

        self.assertEqual(response, {"ok": True})
        self.assertFalse(model_load_called["value"])
        self.assertEqual(app.jobs[job_id].status, "error")
        self.assertEqual(payload["done"], True)
        self.assertEqual(payload["step"], "runtime preflight")
        self.assertEqual(
            payload["error"],
            "ColorComic needs more free disk space before processing. Free some space and try again.",
        )

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
