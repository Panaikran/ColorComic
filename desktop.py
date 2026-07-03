"""Desktop launcher for ColorComic using pywebview."""

from __future__ import annotations

import logging
import os
import re
import socket
import sys
import threading
import time
import urllib.request


HOST = "127.0.0.1"
APP_TITLE = "ColorComic"
LOGGER = logging.getLogger("colorcomic.desktop")
SAFE_JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def find_free_port() -> int:
    """Ask the OS for an available loopback port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return sock.getsockname()[1]


def build_backend_url(port: int) -> str:
    """Build the local backend URL for *port*."""
    return f"http://{HOST}:{port}"


def wait_for_backend(base_url: str, timeout: float = 30.0, interval: float = 0.2) -> None:
    """Poll the health endpoint until the backend responds or timeout expires."""
    deadline = time.monotonic() + timeout
    health_url = f"{base_url}/api/health"
    last_error = None

    while time.monotonic() <= deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = exc
        if interval:
            time.sleep(interval)

    raise RuntimeError(
        f"Backend did not become ready at {health_url}. Last error: {last_error}"
    )


def start_backend(port: int) -> threading.Thread:
    """Start the Flask backend on a daemon thread."""
    from app import create_app

    flask_app = create_app()

    def run_server() -> None:
        flask_app.run(
            host=HOST,
            port=port,
            debug=False,
            threaded=True,
            use_reloader=False,
        )

    thread = threading.Thread(target=run_server, name="ColorComicBackend", daemon=True)
    thread.start()
    return thread


def configure_webview_downloads(webview_module) -> None:
    """Enable native save dialogs for attachment downloads in pywebview."""
    webview_module.settings["ALLOW_DOWNLOADS"] = True


def resolve_output_folder(job_id: str, output_root: str | None = None) -> str:
    """Return the runtime output folder for *job_id*, rejecting path escapes."""
    if not isinstance(job_id, str) or not SAFE_JOB_ID_PATTERN.fullmatch(job_id):
        raise ValueError("Invalid job id")

    if output_root is None:
        from config import Config

        output_root = Config.OUTPUT_FOLDER

    output_root_abs = os.path.abspath(output_root)
    output_folder = os.path.abspath(os.path.join(output_root_abs, job_id))
    if os.path.commonpath([output_root_abs, output_folder]) != output_root_abs:
        raise ValueError("Output folder escapes the runtime output directory")
    return output_folder


class DesktopApi:
    """Methods exposed to the pywebview JavaScript bridge."""

    def __init__(self, output_root: str | None = None, opener=None):
        self._output_root = output_root
        self._opener = opener or os.startfile

    def open_output_folder(self, job_id: str) -> dict:
        try:
            output_folder = resolve_output_folder(job_id, output_root=self._output_root)
            if not os.path.isdir(output_folder):
                return {"ok": False, "error": "Output folder not found.", "path": output_folder}
            self._opener(output_folder)
            return {"ok": True, "path": output_folder}
        except Exception as exc:
            LOGGER.exception("Failed to open output folder for job %r", job_id)
            return {"ok": False, "error": str(exc)}


def launch_desktop() -> None:
    """Start Flask, wait for readiness, then open the pywebview shell."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    port = find_free_port()
    backend_url = build_backend_url(port)

    try:
        backend_thread = start_backend(port)
        wait_for_backend(backend_url)
        if not backend_thread.is_alive():
            raise RuntimeError("Backend thread exited before the desktop window opened.")
    except Exception:
        LOGGER.exception("Failed to start ColorComic backend.")
        raise

    try:
        import webview
    except ImportError as exc:
        raise RuntimeError(
            "pywebview is not installed. Install desktop dependencies with "
            "`pip install -r requirements-desktop.txt`."
        ) from exc

    configure_webview_downloads(webview)
    webview.create_window(APP_TITLE, backend_url, js_api=DesktopApi())
    webview.start()


def main() -> int:
    """Command-line entrypoint."""
    try:
        launch_desktop()
        return 0
    except Exception as exc:
        print(f"ColorComic desktop failed to start: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
