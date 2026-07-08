"""Local JSON storage for ColorComic user preferences."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from typing import Any


PREFERENCES_FILENAME = "preferences.json"

DEFAULT_PREFERENCES: dict[str, Any] = {
    "schema_version": 1,
    "default_mode": "auto",
    "default_device": "cpu",
    "open_output_folder_after_completion": False,
}

_VALID_MODES = {"auto", "reference"}
_VALID_DEVICES = {"cpu", "auto"}


def get_preferences_path(config_dir: str | None = None) -> str:
    if config_dir is None:
        from config import Config

        config_dir = Config.CONFIG_DIR
    return os.path.join(config_dir, PREFERENCES_FILENAME)


def default_preferences() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_PREFERENCES)


def normalize_preferences(payload: object) -> dict[str, Any]:
    preferences = default_preferences()
    if not isinstance(payload, dict):
        return preferences

    if payload.get("schema_version") == DEFAULT_PREFERENCES["schema_version"]:
        preferences["schema_version"] = payload["schema_version"]

    default_mode = payload.get("default_mode")
    if default_mode in _VALID_MODES:
        preferences["default_mode"] = default_mode

    default_device = payload.get("default_device")
    if default_device in _VALID_DEVICES:
        preferences["default_device"] = default_device

    open_output_folder = payload.get("open_output_folder_after_completion")
    if isinstance(open_output_folder, bool):
        preferences["open_output_folder_after_completion"] = open_output_folder

    return preferences


def load_preferences(path: str | None = None) -> dict[str, Any]:
    preferences_path = path or get_preferences_path()
    try:
        with open(preferences_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default_preferences()

    return normalize_preferences(payload)


def save_preferences(preferences: dict[str, Any], path: str | None = None) -> dict[str, Any]:
    normalized = normalize_preferences(preferences)
    preferences_path = path or get_preferences_path()
    preferences_dir = os.path.dirname(preferences_path)
    os.makedirs(preferences_dir, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(
        prefix=f".{PREFERENCES_FILENAME}.",
        suffix=".tmp",
        dir=preferences_dir,
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(normalized, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_path, preferences_path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise

    return normalized


def reset_preferences(path: str | None = None) -> dict[str, Any]:
    return save_preferences(default_preferences(), path)
