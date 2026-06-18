"""Path helpers for read-only app resources and writable runtime data."""

from __future__ import annotations

import os
import sys


APP_NAME = "ColorComic"


def get_app_base_dir() -> str:
    """Return the directory containing bundled or source app resources."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_runtime_dir() -> str:
    """Return the per-user writable runtime directory."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(local_app_data, APP_NAME)


def ensure_directories(*paths: str) -> None:
    """Create each directory if it does not already exist."""
    for path in paths:
        os.makedirs(path, exist_ok=True)

