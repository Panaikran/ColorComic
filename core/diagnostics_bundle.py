"""Create local diagnostics ZIP bundles without user data or model caches."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import zipfile


MAX_LOG_BYTES = 1024 * 1024
LOG_SUFFIXES = (".log", ".txt")


def create_diagnostics_bundle(
    diagnostics: dict,
    log_dir: str,
    app_version: str = "unknown",
    max_log_bytes: int = MAX_LOG_BYTES,
) -> str:
    os.makedirs(log_dir, exist_ok=True)
    generated_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundle_path = os.path.join(log_dir, f"ColorComic-diagnostics-{generated_at}.zip")
    runtime_paths = diagnostics.get("paths", {}) if isinstance(diagnostics, dict) else {}

    manifest = {
        "app": "ColorComic",
        "version": app_version,
        "generated_at": generated_at,
        "runtime_paths": runtime_paths,
    }

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("diagnostics.json", json.dumps(diagnostics, indent=2, sort_keys=True))
        bundle.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        for path in _small_log_files(log_dir, max_log_bytes=max_log_bytes):
            bundle.write(path, os.path.join("logs", os.path.basename(path)))

    return bundle_path


def _small_log_files(log_dir: str, max_log_bytes: int) -> list[str]:
    try:
        names = os.listdir(log_dir)
    except OSError:
        return []

    paths = []
    for name in names:
        path = os.path.join(log_dir, name)
        if not os.path.isfile(path):
            continue
        if not name.lower().endswith(LOG_SUFFIXES):
            continue
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if size <= max_log_bytes:
            paths.append(path)
    return sorted(paths, key=os.path.getmtime, reverse=True)[:5]
