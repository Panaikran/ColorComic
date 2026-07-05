import importlib
import os
import sys
import tempfile
import types
import unittest

from core.batch_queue import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    create_batch,
    transition_job,
)


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


def make_job(job_id, pdf_path, status="uploaded", page_count=2, mode="auto", output_pdf=None, error=None):
    job = types.SimpleNamespace(
        job_id=job_id,
        pdf_path=pdf_path,
        page_count=page_count,
        page_images=[],
        colorized_images=[],
        output_pdf=output_pdf,
        status=status,
        progress=0.0,
        current_step="",
        style="auto",
        device="cpu",
        mode=mode,
        reference_image_path=None,
    )
    if error:
        job.error = error
    return job


class QueueApiTests(unittest.TestCase):
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
        self.app_module.batches.clear()
        for name in self.modules_to_clear:
            sys.modules.pop(name, None)

    def test_batch_status_returns_summary_and_job_rows(self):
        app = self.app_module
        app.jobs["job-1"] = make_job("job-1", r"C:\uploads\first.pdf")
        app.jobs["job-2"] = make_job("job-2", r"C:\uploads\second.pdf")
        batch = create_batch("batch-1", ["job-1", "job-2"], now="2026-07-05T01:00:00Z")
        batch = transition_job(batch, "job-1", STATUS_RUNNING, now="2026-07-05T01:01:00Z")
        app.batches["batch-1"] = batch

        response = self.flask_app.routes["/api/batches/<batch_id>"]("batch-1")

        self.assertEqual(response["batch_id"], "batch-1")
        self.assertEqual(response["status"], STATUS_RUNNING)
        self.assertEqual(response["created_at"], "2026-07-05T01:00:00Z")
        self.assertEqual(response["started_at"], "2026-07-05T01:01:00Z")
        self.assertIsNone(response["completed_at"])
        self.assertEqual(response["counts"], {
            "queued": 1,
            "running": 1,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
            "total": 2,
        })
        self.assertEqual([job["job_id"] for job in response["jobs"]], ["job-1", "job-2"])
        self.assertEqual(response["jobs"][0]["original_filename"], "first.pdf")
        self.assertEqual(response["jobs"][0]["status"], STATUS_RUNNING)
        self.assertEqual(response["jobs"][0]["page_count"], 2)
        self.assertEqual(response["jobs"][1]["status"], STATUS_QUEUED)

    def test_completed_job_reports_runtime_output_availability(self):
        app = self.app_module
        original_output_folder = app.Config.OUTPUT_FOLDER

        with tempfile.TemporaryDirectory() as temp_dir:
            app.Config.OUTPUT_FOLDER = os.path.join(temp_dir, "output")
            output_dir = os.path.join(app.Config.OUTPUT_FOLDER, "job-1")
            os.makedirs(output_dir, exist_ok=True)
            output_pdf = os.path.join(output_dir, "colorized.pdf")
            with open(output_pdf, "wb") as handle:
                handle.write(b"%PDF-1.4\n")

            app.jobs["job-1"] = make_job("job-1", os.path.join(temp_dir, "first.pdf"), output_pdf=output_pdf)
            batch = create_batch("batch-1", ["job-1"])
            batch = transition_job(batch, "job-1", STATUS_RUNNING)
            batch = transition_job(batch, "job-1", STATUS_COMPLETED)
            app.batches["batch-1"] = batch

            try:
                response = self.flask_app.routes["/api/batches/<batch_id>"]("batch-1")
            finally:
                app.Config.OUTPUT_FOLDER = original_output_folder

        row = response["jobs"][0]
        self.assertTrue(row["output_pdf_exists"])
        self.assertTrue(row["output_pdf_safe"])
        self.assertEqual(row["download_url"], "/api/download/job-1")

    def test_failed_job_includes_error_when_available(self):
        app = self.app_module
        app.jobs["job-1"] = make_job("job-1", "broken.pdf", error="PDF export failed")
        batch = create_batch("batch-1", ["job-1"])
        batch = transition_job(batch, "job-1", STATUS_RUNNING)
        batch = transition_job(batch, "job-1", STATUS_FAILED)
        app.batches["batch-1"] = batch

        response = self.flask_app.routes["/api/batches/<batch_id>"]("batch-1")

        self.assertEqual(response["status"], STATUS_FAILED)
        self.assertEqual(response["jobs"][0]["status"], STATUS_FAILED)
        self.assertEqual(response["jobs"][0]["error"], "PDF export failed")

    def test_missing_batch_returns_404(self):
        response, status = self.flask_app.routes["/api/batches/<batch_id>"]("missing")

        self.assertEqual(status, 404)
        self.assertEqual(response["error"], "Batch not found")


if __name__ == "__main__":
    unittest.main()
