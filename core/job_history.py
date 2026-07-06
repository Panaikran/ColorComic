"""Local JSON storage for completed ColorComic jobs."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import tempfile
from typing import Any


HISTORY_FILENAME = "job_history.json"


@dataclass(frozen=True)
class JobHistoryEntry:
    job_id: str
    original_filename: str
    mode: str
    completed_at: str
    output_pdf_path: str
    page_count: int | None = None
    batch_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "job_id": self.job_id,
            "original_filename": self.original_filename,
            "mode": self.mode,
            "completed_at": self.completed_at,
            "output_pdf_path": self.output_pdf_path,
        }
        if self.page_count is not None:
            payload["page_count"] = self.page_count
        if self.batch_id:
            payload["batch_id"] = self.batch_id
        return payload

    @classmethod
    def from_dict(cls, payload: object) -> "JobHistoryEntry | None":
        if not isinstance(payload, dict):
            return None

        required = ("job_id", "original_filename", "mode", "completed_at", "output_pdf_path")
        if not all(isinstance(payload.get(field), str) and payload.get(field) for field in required):
            return None

        page_count = payload.get("page_count")
        if page_count is not None:
            if not isinstance(page_count, int) or page_count < 0:
                return None

        batch_id = payload.get("batch_id")
        if batch_id is not None and (not isinstance(batch_id, str) or not batch_id):
            return None

        return cls(
            job_id=payload["job_id"],
            original_filename=payload["original_filename"],
            mode=payload["mode"],
            completed_at=payload["completed_at"],
            output_pdf_path=payload["output_pdf_path"],
            page_count=page_count,
            batch_id=batch_id,
        )


def get_history_path(config_dir: str | None = None) -> str:
    if config_dir is None:
        from config import Config

        config_dir = Config.CONFIG_DIR
    return os.path.join(config_dir, HISTORY_FILENAME)


def load_job_history(path: str | None = None) -> list[JobHistoryEntry]:
    history_path = path or get_history_path()
    try:
        with open(history_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(payload, list):
        return []

    entries = []
    for item in payload:
        entry = JobHistoryEntry.from_dict(item)
        if entry is not None:
            entries.append(entry)
    return entries


def save_job_history(entries: list[JobHistoryEntry], path: str | None = None) -> None:
    history_path = path or get_history_path()
    history_dir = os.path.dirname(history_path)
    os.makedirs(history_dir, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(
        prefix=f".{HISTORY_FILENAME}.",
        suffix=".tmp",
        dir=history_dir,
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump([entry.as_dict() for entry in entries], handle, indent=2)
            handle.write("\n")
        os.replace(temp_path, history_path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def append_job_history(
    entry: JobHistoryEntry,
    path: str | None = None,
    limit: int = 50,
) -> list[JobHistoryEntry]:
    entries = [existing for existing in load_job_history(path) if existing.job_id != entry.job_id]
    entries.insert(0, entry)
    if limit > 0:
        entries = entries[:limit]
    save_job_history(entries, path)
    return entries


def remove_job_history_entry(job_id: str, path: str | None = None) -> list[JobHistoryEntry]:
    entries = load_job_history(path)
    remaining = [entry for entry in entries if entry.job_id != job_id]
    if len(remaining) != len(entries):
        save_job_history(remaining, path)
    return remaining
