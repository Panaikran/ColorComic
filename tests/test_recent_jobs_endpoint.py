import importlib
import json
import os
import sys
import tempfile
import types
import unittest

from core.job_history import JobHistoryEntry, save_job_history


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


class RecentJobsEndpointTests(unittest.TestCase):
    def setUp(self):
        for name in ("app", "flask", "dotenv"):
            sys.modules.pop(name, None)
        install_fake_flask()
        self.app_module = importlib.import_module("app")
        self.flask_app = self.app_module.create_app()

    def tearDown(self):
        self.app_module.jobs.clear()
        self.app_module.job_queues.clear()
        for name in ("app", "flask", "dotenv"):
            sys.modules.pop(name, None)

    def make_entry(self, job_id, completed_at, output_pdf_path, page_count=1):
        return JobHistoryEntry(
            job_id=job_id,
            original_filename=f"{job_id}.pdf",
            mode="auto",
            completed_at=completed_at,
            output_pdf_path=output_pdf_path,
            page_count=page_count,
        )

    def test_recent_jobs_returns_newest_first_with_output_existence(self):
        original_config_dir = self.app_module.Config.CONFIG_DIR
        original_output_folder = self.app_module.Config.OUTPUT_FOLDER

        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = os.path.join(temp_dir, "config")
            output_folder = os.path.join(temp_dir, "output")
            older_pdf = os.path.join(output_folder, "old-job", "colorized.pdf")
            newer_pdf = os.path.join(output_folder, "new-job", "colorized.pdf")
            os.makedirs(os.path.dirname(older_pdf), exist_ok=True)
            os.makedirs(os.path.dirname(newer_pdf), exist_ok=True)
            with open(older_pdf, "wb") as handle:
                handle.write(b"%PDF-1.4\n")
            with open(newer_pdf, "wb") as handle:
                handle.write(b"%PDF-1.4\n")

            save_job_history(
                [
                    self.make_entry("old-job", "2026-07-03T10:00:00Z", older_pdf),
                    self.make_entry("new-job", "2026-07-03T12:00:00Z", newer_pdf, page_count=2),
                ],
                os.path.join(config_dir, "job_history.json"),
            )
            self.app_module.Config.CONFIG_DIR = config_dir
            self.app_module.Config.OUTPUT_FOLDER = output_folder

            try:
                payload = self.flask_app.routes["/api/recent-jobs"]()
            finally:
                self.app_module.Config.CONFIG_DIR = original_config_dir
                self.app_module.Config.OUTPUT_FOLDER = original_output_folder

        self.assertEqual([job["job_id"] for job in payload["jobs"]], ["new-job", "old-job"])
        self.assertEqual(payload["jobs"][0]["output_pdf_path"], newer_pdf)
        self.assertTrue(payload["jobs"][0]["output_pdf_exists"])
        self.assertTrue(payload["jobs"][0]["output_pdf_safe"])
        self.assertEqual(payload["jobs"][0]["page_count"], 2)

    def test_recent_jobs_marks_missing_output_file(self):
        original_config_dir = self.app_module.Config.CONFIG_DIR
        original_output_folder = self.app_module.Config.OUTPUT_FOLDER

        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = os.path.join(temp_dir, "config")
            output_folder = os.path.join(temp_dir, "output")
            missing_pdf = os.path.join(output_folder, "missing-job", "colorized.pdf")
            save_job_history(
                [self.make_entry("missing-job", "2026-07-03T12:00:00Z", missing_pdf)],
                os.path.join(config_dir, "job_history.json"),
            )
            self.app_module.Config.CONFIG_DIR = config_dir
            self.app_module.Config.OUTPUT_FOLDER = output_folder

            try:
                payload = self.flask_app.routes["/api/recent-jobs"]()
            finally:
                self.app_module.Config.CONFIG_DIR = original_config_dir
                self.app_module.Config.OUTPUT_FOLDER = original_output_folder

        self.assertEqual(payload["jobs"][0]["job_id"], "missing-job")
        self.assertFalse(payload["jobs"][0]["output_pdf_exists"])
        self.assertTrue(payload["jobs"][0]["output_pdf_safe"])

    def test_recent_jobs_handles_corrupt_history_file(self):
        original_config_dir = self.app_module.Config.CONFIG_DIR

        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = os.path.join(temp_dir, "config")
            os.makedirs(config_dir, exist_ok=True)
            with open(os.path.join(config_dir, "job_history.json"), "w", encoding="utf-8") as handle:
                handle.write("{bad json")
            self.app_module.Config.CONFIG_DIR = config_dir

            try:
                payload = self.flask_app.routes["/api/recent-jobs"]()
            finally:
                self.app_module.Config.CONFIG_DIR = original_config_dir

        self.assertEqual(payload, {"jobs": []})

    def test_recent_jobs_marks_paths_outside_output_folder_as_unsafe(self):
        original_config_dir = self.app_module.Config.CONFIG_DIR
        original_output_folder = self.app_module.Config.OUTPUT_FOLDER

        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = os.path.join(temp_dir, "config")
            output_folder = os.path.join(temp_dir, "output")
            outside_pdf = os.path.join(temp_dir, "outside", "colorized.pdf")
            os.makedirs(os.path.dirname(outside_pdf), exist_ok=True)
            with open(outside_pdf, "wb") as handle:
                handle.write(b"%PDF-1.4\n")
            save_job_history(
                [self.make_entry("unsafe-job", "2026-07-03T12:00:00Z", outside_pdf)],
                os.path.join(config_dir, "job_history.json"),
            )
            self.app_module.Config.CONFIG_DIR = config_dir
            self.app_module.Config.OUTPUT_FOLDER = output_folder

            try:
                payload = self.flask_app.routes["/api/recent-jobs"]()
            finally:
                self.app_module.Config.CONFIG_DIR = original_config_dir
                self.app_module.Config.OUTPUT_FOLDER = original_output_folder

        self.assertEqual(payload["jobs"][0]["job_id"], "unsafe-job")
        self.assertIsNone(payload["jobs"][0]["output_pdf_path"])
        self.assertFalse(payload["jobs"][0]["output_pdf_exists"])
        self.assertFalse(payload["jobs"][0]["output_pdf_safe"])


if __name__ == "__main__":
    unittest.main()
