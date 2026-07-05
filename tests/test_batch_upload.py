import importlib
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


class FakeFiles:
    def __init__(self, files):
        self._files = files

    def getlist(self, key):
        return self._files if key == "files" else []


class FakeUpload:
    def __init__(self, filename, content=b"%PDF-1.4\n"):
        self.filename = filename
        self.content = content

    def save(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(self.content)


def install_fake_flask():
    fake_flask = types.ModuleType("flask")
    fake_flask.Flask = FakeFlask
    fake_flask.Response = lambda *args, **kwargs: ("response", args, kwargs)
    fake_flask.jsonify = lambda payload=None, **kwargs: payload if payload is not None else kwargs
    fake_flask.redirect = lambda target: ("redirect", target)
    fake_flask.render_template = lambda template, **kwargs: ("template", template, kwargs)
    fake_flask.request = types.SimpleNamespace(files=FakeFiles([]), form={})
    fake_flask.send_file = lambda *args, **kwargs: ("send_file", args, kwargs)
    fake_flask.url_for = lambda endpoint: f"/{endpoint}"
    sys.modules["flask"] = fake_flask

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *args, **kwargs: True
    sys.modules["dotenv"] = fake_dotenv
    return fake_flask


def install_fake_pdf_handler(failing_names=(), zero_page_names=()):
    fake_pdf_handler = types.ModuleType("core.pdf_handler")
    failing_names = set(failing_names)
    zero_page_names = set(zero_page_names)

    def get_page_count(pdf_path):
        basename = os.path.basename(pdf_path)
        if basename in failing_names:
            raise ValueError("invalid PDF")
        if basename in zero_page_names:
            return 0
        return 2

    def extract_pages(pdf_path, pages_dir, dpi):
        os.makedirs(pages_dir, exist_ok=True)
        return [
            os.path.join(pages_dir, "page_0000.png"),
            os.path.join(pages_dir, "page_0001.png"),
        ]

    fake_pdf_handler.get_page_count = get_page_count
    fake_pdf_handler.extract_pages = extract_pages
    sys.modules["core.pdf_handler"] = fake_pdf_handler


class BatchUploadRouteTests(unittest.TestCase):
    def setUp(self):
        self.modules_to_clear = ("app", "flask", "dotenv", "core.pdf_handler")
        for name in self.modules_to_clear:
            sys.modules.pop(name, None)
        self.fake_flask = install_fake_flask()
        install_fake_pdf_handler()
        self.app_module = importlib.import_module("app")
        self.flask_app = self.app_module.create_app()

    def tearDown(self):
        self.app_module.jobs.clear()
        self.app_module.job_queues.clear()
        self.app_module.batches.clear()
        for name in self.modules_to_clear:
            sys.modules.pop(name, None)

    def set_uuid_values(self, *values):
        app = self.app_module
        original_uuid4 = app.uuid.uuid4
        iterator = iter(values)
        app.uuid.uuid4 = lambda: next(iterator)
        return original_uuid4

    def test_batch_upload_accepts_valid_auto_pdfs_and_reports_invalid_files(self):
        app = self.app_module
        original_upload_folder = app.Config.UPLOAD_FOLDER
        original_output_folder = app.Config.OUTPUT_FOLDER
        original_uuid4 = self.set_uuid_values("batch-abc123", "job-0000001", "job-0000002")

        with tempfile.TemporaryDirectory() as temp_dir:
            app.Config.UPLOAD_FOLDER = os.path.join(temp_dir, "uploads")
            app.Config.OUTPUT_FOLDER = os.path.join(temp_dir, "output")
            self.fake_flask.request.files = FakeFiles([
                FakeUpload("First.pdf"),
                FakeUpload("notes.txt"),
                FakeUpload("..\\Unsafe:Name.pdf"),
            ])
            self.fake_flask.request.form = {"mode": "auto", "style": "manga", "device": "cpu"}

            try:
                response = self.flask_app.routes["/api/batches"]()
            finally:
                app.Config.UPLOAD_FOLDER = original_upload_folder
                app.Config.OUTPUT_FOLDER = original_output_folder
                app.uuid.uuid4 = original_uuid4

        self.assertEqual(response["batch_id"], "batch-abc123")
        self.assertEqual([job["job_id"] for job in response["jobs"]], ["job-0000001", "job-0000002"])
        self.assertEqual(response["errors"], [
            {
                "filename": "notes.txt",
                "code": "not_pdf",
                "message": "Only PDF files are accepted.",
            }
        ])
        self.assertIn("batch-abc123", app.batches)
        self.assertEqual(app.batches["batch-abc123"].job_ids, ("job-0000001", "job-0000002"))
        self.assertEqual(app.jobs["job-0000001"].mode, "auto")
        self.assertEqual(app.jobs["job-0000001"].style, "manga")
        self.assertEqual(app.jobs["job-0000001"].device, "cpu")
        self.assertTrue(app.jobs["job-0000002"].pdf_path.endswith("Unsafe_Name.pdf"))

    def test_batch_upload_continues_after_pdf_preparation_error(self):
        app = self.app_module
        original_upload_folder = app.Config.UPLOAD_FOLDER
        original_output_folder = app.Config.OUTPUT_FOLDER
        original_uuid4 = self.set_uuid_values("batch-abc123", "job-bad0000", "job-good000")
        install_fake_pdf_handler(failing_names={"bad.pdf"})

        with tempfile.TemporaryDirectory() as temp_dir:
            app.Config.UPLOAD_FOLDER = os.path.join(temp_dir, "uploads")
            app.Config.OUTPUT_FOLDER = os.path.join(temp_dir, "output")
            self.fake_flask.request.files = FakeFiles([
                FakeUpload("bad.pdf"),
                FakeUpload("good.pdf"),
            ])
            self.fake_flask.request.form = {"mode": "auto"}

            try:
                response = self.flask_app.routes["/api/batches"]()
            finally:
                app.Config.UPLOAD_FOLDER = original_upload_folder
                app.Config.OUTPUT_FOLDER = original_output_folder
                app.uuid.uuid4 = original_uuid4

        self.assertEqual(response["batch_id"], "batch-abc123")
        self.assertEqual([job["job_id"] for job in response["jobs"]], ["job-good000"])
        self.assertEqual(response["errors"][0]["filename"], "bad.pdf")
        self.assertEqual(response["errors"][0]["code"], "pdf_unreadable")
        self.assertIn("job-good000", app.jobs)
        self.assertNotIn("job-bad0000", app.jobs)
        self.assertEqual(app.batches["batch-abc123"].job_ids, ("job-good000",))

    def test_batch_upload_rejects_zero_page_pdf_before_job_creation(self):
        app = self.app_module
        original_upload_folder = app.Config.UPLOAD_FOLDER
        original_output_folder = app.Config.OUTPUT_FOLDER
        original_uuid4 = self.set_uuid_values("batch-abc123", "job-empty00", "job-good000")
        install_fake_pdf_handler(zero_page_names={"empty.pdf"})

        with tempfile.TemporaryDirectory() as temp_dir:
            app.Config.UPLOAD_FOLDER = os.path.join(temp_dir, "uploads")
            app.Config.OUTPUT_FOLDER = os.path.join(temp_dir, "output")
            self.fake_flask.request.files = FakeFiles([
                FakeUpload("empty.pdf"),
                FakeUpload("good.pdf"),
            ])
            self.fake_flask.request.form = {"mode": "auto"}

            try:
                response = self.flask_app.routes["/api/batches"]()
            finally:
                app.Config.UPLOAD_FOLDER = original_upload_folder
                app.Config.OUTPUT_FOLDER = original_output_folder
                app.uuid.uuid4 = original_uuid4

        self.assertEqual(response["batch_id"], "batch-abc123")
        self.assertEqual([job["job_id"] for job in response["jobs"]], ["job-good000"])
        self.assertEqual(response["errors"][0]["filename"], "empty.pdf")
        self.assertEqual(response["errors"][0]["code"], "pdf_has_no_pages")
        self.assertEqual(response["errors"][0]["message"], "Choose a PDF with at least one page.")
        self.assertNotIn("job-empty00", app.jobs)

    def test_batch_upload_reports_unwritable_output_preflight_error(self):
        app = self.app_module
        original_upload_folder = app.Config.UPLOAD_FOLDER
        original_preflight = app.validate_colorize_preflight
        original_uuid4 = self.set_uuid_values("batch-abc123", "job-bad0000")

        with tempfile.TemporaryDirectory() as temp_dir:
            app.Config.UPLOAD_FOLDER = os.path.join(temp_dir, "uploads")
            self.fake_flask.request.files = FakeFiles([FakeUpload("input.pdf")])
            self.fake_flask.request.form = {"mode": "auto"}

            def fail_output_preflight(pdf_path, job_id, output_folder, mode):
                return types.SimpleNamespace(
                    ok=False,
                    errors=(
                        types.SimpleNamespace(
                            code="output_not_writable",
                            message="ColorComic cannot write to the output folder.",
                            step="output preflight",
                        ),
                    ),
                    output_dir=os.path.join(output_folder, job_id),
                    page_count=2,
                )

            app.validate_colorize_preflight = fail_output_preflight

            try:
                response, status = self.flask_app.routes["/api/batches"]()
            finally:
                app.Config.UPLOAD_FOLDER = original_upload_folder
                app.validate_colorize_preflight = original_preflight
                app.uuid.uuid4 = original_uuid4

        self.assertEqual(status, 400)
        self.assertIsNone(response["batch_id"])
        self.assertEqual(response["jobs"], [])
        self.assertEqual(response["errors"][0]["filename"], "input.pdf")
        self.assertEqual(response["errors"][0]["code"], "output_not_writable")
        self.assertEqual(response["errors"][0]["step"], "output preflight")
        self.assertEqual(app.jobs, {})
        self.assertEqual(app.batches, {})

    def test_batch_upload_rejects_reference_mode_without_creating_batch(self):
        app = self.app_module
        self.fake_flask.request.files = FakeFiles([FakeUpload("input.pdf")])
        self.fake_flask.request.form = {"mode": "reference"}

        response, status = self.flask_app.routes["/api/batches"]()

        self.assertEqual(status, 400)
        self.assertEqual(response["error"], "Batch uploads support Auto mode only")
        self.assertEqual(app.jobs, {})
        self.assertEqual(app.batches, {})

    def test_batch_upload_returns_errors_when_no_valid_pdfs_are_accepted(self):
        app = self.app_module
        original_upload_folder = app.Config.UPLOAD_FOLDER
        original_output_folder = app.Config.OUTPUT_FOLDER
        original_uuid4 = self.set_uuid_values("batch-abc123")

        with tempfile.TemporaryDirectory() as temp_dir:
            app.Config.UPLOAD_FOLDER = os.path.join(temp_dir, "uploads")
            app.Config.OUTPUT_FOLDER = os.path.join(temp_dir, "output")
            self.fake_flask.request.files = FakeFiles([FakeUpload("notes.txt")])
            self.fake_flask.request.form = {"mode": "auto"}

            try:
                response, status = self.flask_app.routes["/api/batches"]()
            finally:
                app.Config.UPLOAD_FOLDER = original_upload_folder
                app.Config.OUTPUT_FOLDER = original_output_folder
                app.uuid.uuid4 = original_uuid4

        self.assertEqual(status, 400)
        self.assertIsNone(response["batch_id"])
        self.assertEqual(response["jobs"], [])
        self.assertEqual(response["errors"][0]["code"], "not_pdf")
        self.assertEqual(app.jobs, {})
        self.assertEqual(app.batches, {})


if __name__ == "__main__":
    unittest.main()
