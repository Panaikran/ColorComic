import importlib
import socket
import sys
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
            windows=[],
            started=False,
        )

        def create_window(title, url):
            fake_webview.windows.append((title, url))

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
        self.assertEqual(fake_webview.windows, [("ColorComic", "http://127.0.0.1:43210")])
        self.assertTrue(fake_webview.started)
