"""Conservative cleanup for orphaned runtime upload data."""

from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
import time


DEFAULT_ORPHAN_AGE_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class CleanupResult:
    removed: tuple[str, ...]
    errors: tuple[str, ...]


def cleanup_orphaned_uploads(
    uploads_dir: str,
    active_paths: list[str] | tuple[str, ...] = (),
    older_than_seconds: int = DEFAULT_ORPHAN_AGE_SECONDS,
    now: float | None = None,
) -> CleanupResult:
    """Remove old direct children of uploads_dir, preserving active paths."""
    if now is None:
        now = time.time()

    uploads_root = os.path.abspath(uploads_dir)
    active_roots = tuple(os.path.abspath(path) for path in active_paths)
    removed: list[str] = []
    errors: list[str] = []

    try:
        names = os.listdir(uploads_root)
    except OSError:
        return CleanupResult((), ())

    for name in names:
        path = os.path.abspath(os.path.join(uploads_root, name))
        if not _is_child(uploads_root, path) or _contains_active_path(path, active_roots):
            continue
        try:
            age = now - os.path.getmtime(path)
            if age < older_than_seconds:
                continue
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            removed.append(path)
        except OSError as exc:
            errors.append(f"{path}: {exc}")

    return CleanupResult(tuple(removed), tuple(errors))


def _is_child(root: str, path: str) -> bool:
    try:
        return os.path.normcase(os.path.commonpath([root, path])) == os.path.normcase(root)
    except ValueError:
        return False


def _contains_active_path(candidate: str, active_paths: tuple[str, ...]) -> bool:
    return any(_is_child(candidate, active) for active in active_paths)
