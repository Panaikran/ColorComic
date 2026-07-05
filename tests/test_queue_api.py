import importlib
import os
import sys
import tempfile
import types
import unittest

from core.batch_queue import (
    BatchRecord,
    STATUS_CANCELLED,
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


class ImmediateThread:
    def __init__(self, target, daemon=False):
        self.target = target
        self.daemon = daemon

    def start(self):
        self.target()


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
        self.app_module.active_batch_runners.clear()
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

    def test_batch_start_processes_queued_jobs(self):
        app = self.app_module
        original_thread = app.threading.Thread
        original_worker = app._run_colorization_job
        original_output_folder = app.Config.OUTPUT_FOLDER
        order = []

        with tempfile.TemporaryDirectory() as temp_dir:
            app.Config.OUTPUT_FOLDER = os.path.join(temp_dir, "output")
            app.jobs["job-1"] = make_job("job-1", "first.pdf")
            app.jobs["job-2"] = make_job("job-2", "second.pdf")
            app.batches["batch-1"] = create_batch("batch-1", ["job-1", "job-2"])
            app.threading.Thread = ImmediateThread
            app._run_colorization_job = lambda job_id, job, event_queue, out_dir: order.append(job_id) or True

            try:
                response = self.flask_app.routes["/api/batches/<batch_id>/start"]("batch-1")
            finally:
                app.threading.Thread = original_thread
                app._run_colorization_job = original_worker
                app.Config.OUTPUT_FOLDER = original_output_folder

        self.assertEqual(response["ok"], True)
        self.assertEqual(response["batch_id"], "batch-1")
        self.assertEqual(response["status"], "started")
        self.assertEqual(order, ["job-1", "job-2"])
        self.assertEqual(app.batches["batch-1"].status, STATUS_COMPLETED)
        self.assertEqual(app.batches["batch-1"].counts.completed, 2)
        self.assertEqual(app.active_batch_runners, {})

    def test_batch_start_rejects_duplicate_running_batch(self):
        app = self.app_module
        app.jobs["job-1"] = make_job("job-1", "first.pdf")
        batch = create_batch("batch-1", ["job-1"])
        app.batches["batch-1"] = transition_job(batch, "job-1", STATUS_RUNNING)

        response, status = self.flask_app.routes["/api/batches/<batch_id>/start"]("batch-1")

        self.assertEqual(status, 409)
        self.assertEqual(response["error"], "Batch is already running")

    def test_batch_start_missing_batch_returns_404(self):
        response, status = self.flask_app.routes["/api/batches/<batch_id>/start"]("missing")

        self.assertEqual(status, 404)
        self.assertEqual(response["error"], "Batch not found")

    def test_batch_start_rejects_empty_batch(self):
        app = self.app_module
        app.batches["empty"] = BatchRecord(
            batch_id="empty",
            job_ids=(),
            job_statuses={},
            status=STATUS_QUEUED,
            created_at="2026-07-05T01:00:00Z",
        )

        response, status = self.flask_app.routes["/api/batches/<batch_id>/start"]("empty")

        self.assertEqual(status, 400)
        self.assertEqual(response["error"], "Batch has no queued jobs")

    def test_batch_start_continues_after_job_failure(self):
        app = self.app_module
        original_thread = app.threading.Thread
        original_worker = app._run_colorization_job
        original_output_folder = app.Config.OUTPUT_FOLDER
        order = []

        with tempfile.TemporaryDirectory() as temp_dir:
            app.Config.OUTPUT_FOLDER = os.path.join(temp_dir, "output")
            app.jobs["job-1"] = make_job("job-1", "first.pdf")
            app.jobs["job-2"] = make_job("job-2", "second.pdf")
            app.jobs["job-3"] = make_job("job-3", "third.pdf")
            app.batches["batch-1"] = create_batch("batch-1", ["job-1", "job-2", "job-3"])
            app.threading.Thread = ImmediateThread

            def worker(job_id, job, event_queue, out_dir):
                order.append(job_id)
                return job_id != "job-2"

            app._run_colorization_job = worker

            try:
                response = self.flask_app.routes["/api/batches/<batch_id>/start"]("batch-1")
            finally:
                app.threading.Thread = original_thread
                app._run_colorization_job = original_worker
                app.Config.OUTPUT_FOLDER = original_output_folder

        self.assertEqual(response["ok"], True)
        self.assertEqual(order, ["job-1", "job-2", "job-3"])
        self.assertEqual(app.batches["batch-1"].status, STATUS_FAILED)
        self.assertEqual(app.batches["batch-1"].job_statuses["job-1"], STATUS_COMPLETED)
        self.assertEqual(app.batches["batch-1"].job_statuses["job-2"], STATUS_FAILED)
        self.assertEqual(app.batches["batch-1"].job_statuses["job-3"], STATUS_COMPLETED)

    def test_cancel_queued_batch_job_updates_counts(self):
        app = self.app_module
        app.jobs["job-1"] = make_job("job-1", "first.pdf")
        app.jobs["job-2"] = make_job("job-2", "second.pdf")
        app.batches["batch-1"] = create_batch("batch-1", ["job-1", "job-2"])

        response = self.flask_app.routes["/api/batches/<batch_id>/jobs/<job_id>/cancel"]("batch-1", "job-2")

        self.assertEqual(response["ok"], True)
        self.assertEqual(response["batch_id"], "batch-1")
        self.assertEqual(response["job_id"], "job-2")
        self.assertEqual(response["status"], STATUS_CANCELLED)
        self.assertEqual(app.batches["batch-1"].job_statuses["job-2"], STATUS_CANCELLED)
        self.assertEqual(app.batches["batch-1"].counts.queued, 1)
        self.assertEqual(app.batches["batch-1"].counts.cancelled, 1)
        self.assertIn("job-2", app.jobs)

    def test_cancel_rejects_running_batch_job(self):
        app = self.app_module
        app.jobs["job-1"] = make_job("job-1", "first.pdf")
        batch = create_batch("batch-1", ["job-1"])
        app.batches["batch-1"] = transition_job(batch, "job-1", STATUS_RUNNING)

        response, status = self.flask_app.routes["/api/batches/<batch_id>/jobs/<job_id>/cancel"]("batch-1", "job-1")

        self.assertEqual(status, 409)
        self.assertEqual(response["error"], "Job is already running")
        self.assertEqual(app.batches["batch-1"].job_statuses["job-1"], STATUS_RUNNING)

    def test_cancel_rejects_completed_batch_job(self):
        app = self.app_module
        app.jobs["job-1"] = make_job("job-1", "first.pdf")
        batch = create_batch("batch-1", ["job-1"])
        batch = transition_job(batch, "job-1", STATUS_RUNNING)
        app.batches["batch-1"] = transition_job(batch, "job-1", STATUS_COMPLETED)

        response, status = self.flask_app.routes["/api/batches/<batch_id>/jobs/<job_id>/cancel"]("batch-1", "job-1")

        self.assertEqual(status, 409)
        self.assertEqual(response["error"], "Job is already completed")
        self.assertEqual(app.batches["batch-1"].job_statuses["job-1"], STATUS_COMPLETED)

    def test_cancel_rejects_already_cancelled_batch_job(self):
        app = self.app_module
        app.jobs["job-1"] = make_job("job-1", "first.pdf")
        batch = create_batch("batch-1", ["job-1"])
        app.batches["batch-1"] = transition_job(batch, "job-1", STATUS_CANCELLED)

        response, status = self.flask_app.routes["/api/batches/<batch_id>/jobs/<job_id>/cancel"]("batch-1", "job-1")

        self.assertEqual(status, 409)
        self.assertEqual(response["error"], "Job is already cancelled")
        self.assertEqual(app.batches["batch-1"].job_statuses["job-1"], STATUS_CANCELLED)

    def test_cancel_missing_batch_returns_404(self):
        response, status = self.flask_app.routes["/api/batches/<batch_id>/jobs/<job_id>/cancel"]("missing", "job-1")

        self.assertEqual(status, 404)
        self.assertEqual(response["error"], "Batch not found")

    def test_cancel_missing_job_returns_404(self):
        app = self.app_module
        app.batches["batch-1"] = create_batch("batch-1", ["job-1"])

        response, status = self.flask_app.routes["/api/batches/<batch_id>/jobs/<job_id>/cancel"]("batch-1", "missing")

        self.assertEqual(status, 404)
        self.assertEqual(response["error"], "Job not found")


if __name__ == "__main__":
    unittest.main()
