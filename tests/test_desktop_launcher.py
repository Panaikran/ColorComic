import importlib
import os
import socket
import sys
import tempfile
import types
import unittest
from unittest import mock


class DesktopLauncherTests(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop("desktop", None)
        sys.modules.pop("webview", None)

    def test_import_does_not_require_pywebview(self):
        sys.modules.pop("webview", None)

        desktop = importlib.import_module("desktop")

        self.assertTrue(hasattr(desktop, "main"))
        self.assertNotIn("webview", sys.modules)

    def test_find_free_port_returns_available_local_port(self):
        desktop = importlib.import_module("desktop")

        port = desktop.find_free_port()

        self.assertIsInstance(port, int)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", port))

    def test_build_backend_url_uses_loopback_and_port(self):
        desktop = importlib.import_module("desktop")

        self.assertEqual(desktop.build_backend_url(54321), "http://127.0.0.1:54321")

    def test_configure_webview_downloads_enables_native_save_dialogs(self):
        desktop = importlib.import_module("desktop")
        fake_webview = types.SimpleNamespace(settings={"ALLOW_DOWNLOADS": False})

        desktop.configure_webview_downloads(fake_webview)

        self.assertTrue(fake_webview.settings["ALLOW_DOWNLOADS"])

    def test_resolve_output_folder_stays_inside_output_root(self):
        desktop = importlib.import_module("desktop")

        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = os.path.join(temp_dir, "output")
            expected = os.path.join(output_root, "abc-123")

            self.assertEqual(
                desktop.resolve_output_folder("abc-123", output_root=output_root),
                os.path.abspath(expected),
            )

    def test_resolve_output_folder_rejects_path_escape(self):
        desktop = importlib.import_module("desktop")

        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = os.path.join(temp_dir, "output")

            with self.assertRaisesRegex(ValueError, "Invalid job id"):
                desktop.resolve_output_folder("..\\outside", output_root=output_root)

            with self.assertRaisesRegex(ValueError, "Invalid job id"):
                desktop.resolve_output_folder("../outside", output_root=output_root)

    def test_resolve_output_pdf_stays_inside_output_root(self):
        desktop = importlib.import_module("desktop")

        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = os.path.join(temp_dir, "output")
            expected = os.path.join(output_root, "job-1", "colorized.pdf")

            self.assertEqual(
                desktop.resolve_output_pdf("job-1", output_root=output_root),
                os.path.abspath(expected),
            )

    def test_desktop_api_opens_existing_output_folder(self):
        desktop = importlib.import_module("desktop")
        opened = []

        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = os.path.join(temp_dir, "output")
            output_folder = os.path.join(output_root, "job-1")
            os.makedirs(output_folder)
            api = desktop.DesktopApi(output_root=output_root, opener=opened.append)

            result = api.open_output_folder("job-1")

        self.assertEqual(result["ok"], True)
        self.assertEqual(opened, [os.path.abspath(output_folder)])

    def test_desktop_api_reports_missing_output_folder(self):
        desktop = importlib.import_module("desktop")
        opened = []

        with tempfile.TemporaryDirectory() as temp_dir:
            api = desktop.DesktopApi(output_root=os.path.join(temp_dir, "output"), opener=opened.append)

            result = api.open_output_folder("missing")

        self.assertEqual(result["ok"], False)
        self.assertIn("not found", result["error"])
        self.assertEqual(opened, [])

    def test_desktop_api_reveals_existing_output_pdf(self):
        desktop = importlib.import_module("desktop")
        revealed = []

        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = os.path.join(temp_dir, "output")
            output_folder = os.path.join(output_root, "job-1")
            os.makedirs(output_folder)
            output_pdf = os.path.join(output_folder, "colorized.pdf")
            with open(output_pdf, "wb") as handle:
                handle.write(b"%PDF-1.4")
            api = desktop.DesktopApi(output_root=output_root, pdf_revealer=revealed.append)

            result = api.open_output_pdf("job-1")

        self.assertEqual(result["ok"], True)
        self.assertEqual(revealed, [os.path.abspath(output_pdf)])

    def test_desktop_api_reports_missing_output_pdf(self):
        desktop = importlib.import_module("desktop")
        revealed = []

        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = os.path.join(temp_dir, "output")
            os.makedirs(os.path.join(output_root, "job-1"))
            api = desktop.DesktopApi(output_root=output_root, pdf_revealer=revealed.append)

            result = api.open_output_pdf("job-1")

        self.assertEqual(result["ok"], False)
        self.assertIn("not found", result["error"])
        self.assertEqual(revealed, [])

    def test_desktop_api_rejects_invalid_output_pdf_job_id(self):
        desktop = importlib.import_module("desktop")
        revealed = []

        with tempfile.TemporaryDirectory() as temp_dir:
            api = desktop.DesktopApi(output_root=os.path.join(temp_dir, "output"), pdf_revealer=revealed.append)

            with mock.patch.object(desktop.LOGGER, "exception") as log_exception:
                result = api.open_output_pdf("..\\outside")

        self.assertEqual(result["ok"], False)
        self.assertIn("Invalid job id", result["error"])
        self.assertEqual(revealed, [])
        log_exception.assert_called_once()

    def test_wait_for_backend_returns_when_health_is_ready(self):
        desktop = importlib.import_module("desktop")

        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.status = 200

            desktop.wait_for_backend("http://127.0.0.1:12345", timeout=0.1, interval=0)

        urlopen.assert_called_with("http://127.0.0.1:12345/api/health", timeout=1)

    def test_wait_for_backend_raises_useful_error_on_timeout(self):
        desktop = importlib.import_module("desktop")

        with mock.patch("urllib.request.urlopen", side_effect=OSError("not yet")):
            with self.assertRaisesRegex(RuntimeError, "Backend did not become ready"):
                desktop.wait_for_backend("http://127.0.0.1:12345", timeout=0, interval=0)

    def test_launch_desktop_opens_pywebview_to_backend_url(self):
        desktop = importlib.import_module("desktop")
        fake_webview = types.SimpleNamespace(
            settings={"ALLOW_DOWNLOADS": False},
            windows=[],
            started=False,
        )

        def create_window(title, url, **kwargs):
            fake_webview.windows.append((title, url, kwargs))

        def start():
            fake_webview.started = True

        fake_webview.create_window = create_window
        fake_webview.start = start
        sys.modules["webview"] = fake_webview

        backend_thread = types.SimpleNamespace(is_alive=lambda: True)
        with (
            mock.patch.object(desktop, "find_free_port", return_value=43210),
            mock.patch.object(desktop, "start_backend", return_value=backend_thread),
            mock.patch.object(desktop, "wait_for_backend") as wait_for_backend,
        ):
            desktop.launch_desktop()

        wait_for_backend.assert_called_once_with("http://127.0.0.1:43210")
        self.assertEqual(fake_webview.windows[0][0:2], ("ColorComic", "http://127.0.0.1:43210"))
        self.assertIsInstance(fake_webview.windows[0][2]["js_api"], desktop.DesktopApi)
        self.assertTrue(fake_webview.settings["ALLOW_DOWNLOADS"])
        self.assertTrue(fake_webview.started)
