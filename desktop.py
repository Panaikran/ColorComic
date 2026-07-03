"""Desktop launcher for ColorComic using pywebview."""

from __future__ import annotations

import logging
import socket
import sys
import threading
import time
import urllib.request


HOST = "127.0.0.1"
APP_TITLE = "ColorComic"
LOGGER = logging.getLogger("colorcomic.desktop")


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
    webview.create_window(APP_TITLE, backend_url)
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
