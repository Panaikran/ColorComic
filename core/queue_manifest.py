"""Versioned local storage for reconstructable batch queue metadata."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import tempfile
from typing import Callable, Mapping


SCHEMA_VERSION = 1
MANIFEST_FILENAME = "queue_manifest.json"


class QueueManifestStorageError(ValueError):
    """Raised when a manifest cannot be safely replaced."""


@dataclass(frozen=True)
class QueueJobRecord:
    job_id: str
    status: str
    attempt_number: int
    pdf_path: str
    page_images: tuple[str, ...]
    page_count: int
    mode: str
    style: str
    device: str
    retry_of_job_id: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        payload = {
            "job_id": self.job_id,
            "status": self.status,
            "attempt_number": self.attempt_number,
            "pdf_path": self.pdf_path,
            "page_images": list(self.page_images),
            "page_count": self.page_count,
            "mode": self.mode,
            "style": self.style,
            "device": self.device,
        }
        if self.retry_of_job_id:
            payload["retry_of_job_id"] = self.retry_of_job_id
        if self.error:
            payload["error"] = self.error
        return payload

    @classmethod
    def from_dict(cls, payload: object) -> "QueueJobRecord | None":
        if not isinstance(payload, Mapping):
            return None
        required_strings = ("job_id", "status", "pdf_path", "mode", "style", "device")
        if not all(isinstance(payload.get(name), str) and payload[name] for name in required_strings):
            return None
        if not isinstance(payload.get("attempt_number"), int) or payload["attempt_number"] < 1:
            return None
        if not isinstance(payload.get("page_count"), int) or payload["page_count"] < 0:
            return None
        page_images = payload.get("page_images")
        if not isinstance(page_images, list) or not all(isinstance(path, str) and path for path in page_images):
            return None
        retry_of_job_id = payload.get("retry_of_job_id")
        if retry_of_job_id is not None and (not isinstance(retry_of_job_id, str) or not retry_of_job_id):
            return None
        error = payload.get("error")
        if error is not None and not isinstance(error, str):
            return None
        return cls(
            job_id=payload["job_id"],
            status=payload["status"],
            attempt_number=payload["attempt_number"],
            pdf_path=payload["pdf_path"],
            page_images=tuple(page_images),
            page_count=payload["page_count"],
            mode=payload["mode"],
            style=payload["style"],
            device=payload["device"],
            retry_of_job_id=retry_of_job_id,
            error=error,
        )


@dataclass(frozen=True)
class QueueBatchRecord:
    batch_id: str
    job_ids: tuple[str, ...]
    jobs: tuple[QueueJobRecord, ...]
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None

    def as_dict(self) -> dict:
        payload = {
            "batch_id": self.batch_id,
            "job_ids": list(self.job_ids),
            "jobs": [job.as_dict() for job in self.jobs],
            "created_at": self.created_at,
        }
        if self.started_at:
            payload["started_at"] = self.started_at
        if self.completed_at:
            payload["completed_at"] = self.completed_at
        return payload

    @classmethod
    def from_dict(cls, payload: object) -> "QueueBatchRecord | None":
        if not isinstance(payload, Mapping):
            return None
        if not isinstance(payload.get("batch_id"), str) or not payload["batch_id"]:
            return None
        if not isinstance(payload.get("created_at"), str) or not payload["created_at"]:
            return None
        job_ids = payload.get("job_ids")
        jobs_payload = payload.get("jobs")
        if not isinstance(job_ids, list) or not isinstance(jobs_payload, list):
            return None
        if not all(isinstance(job_id, str) and job_id for job_id in job_ids) or len(set(job_ids)) != len(job_ids):
            return None
        jobs = [QueueJobRecord.from_dict(job) for job in jobs_payload]
        if any(job is None for job in jobs):
            return None
        typed_jobs = tuple(job for job in jobs if job is not None)
        if tuple(job.job_id for job in typed_jobs) != tuple(job_ids):
            return None
        started_at = payload.get("started_at")
        completed_at = payload.get("completed_at")
        if started_at is not None and (not isinstance(started_at, str) or not started_at):
            return None
        if completed_at is not None and (not isinstance(completed_at, str) or not completed_at):
            return None
        return cls(
            batch_id=payload["batch_id"],
            job_ids=tuple(job_ids),
            jobs=typed_jobs,
            created_at=payload["created_at"],
            started_at=started_at,
            completed_at=completed_at,
        )


@dataclass(frozen=True)
class QueueManifest:
    batches: tuple[QueueBatchRecord, ...]
    schema_version: int = SCHEMA_VERSION

    def as_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "batches": [batch.as_dict() for batch in self.batches],
        }

    @classmethod
    def from_dict(cls, payload: object) -> "QueueManifest | None":
        if not isinstance(payload, Mapping) or payload.get("schema_version") != SCHEMA_VERSION:
            return None
        batches_payload = payload.get("batches")
        if not isinstance(batches_payload, list):
            return None
        batches = [QueueBatchRecord.from_dict(batch) for batch in batches_payload]
        if any(batch is None for batch in batches):
            return None
        typed_batches = tuple(batch for batch in batches if batch is not None)
        if len({batch.batch_id for batch in typed_batches}) != len(typed_batches):
            return None
        return cls(batches=typed_batches)


ManifestMigrator = Callable[[dict], dict | None]
MIGRATORS: dict[int, ManifestMigrator] = {}


def get_queue_manifest_path(config_dir: str | None = None) -> str:
    if config_dir is None:
        from config import Config

        config_dir = Config.CONFIG_DIR
    return os.path.join(config_dir, MANIFEST_FILENAME)


def migrate_manifest(payload: object) -> dict | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("schema_version"), int):
        return None
    migrated = payload
    while migrated["schema_version"] < SCHEMA_VERSION:
        migrator = MIGRATORS.get(migrated["schema_version"])
        if migrator is None:
            return None
        migrated = migrator(migrated)
        if not isinstance(migrated, dict) or not isinstance(migrated.get("schema_version"), int):
            return None
    return migrated if migrated["schema_version"] == SCHEMA_VERSION else None


def load_queue_manifest(path: str | None = None) -> QueueManifest | None:
    manifest_path = path or get_queue_manifest_path()
    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    migrated = migrate_manifest(payload)
    return QueueManifest.from_dict(migrated)


def _ensure_safe_to_replace(path: str) -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise QueueManifestStorageError("Existing manifest is malformed") from exc
    if migrate_manifest(payload) is None:
        raise QueueManifestStorageError("Existing manifest schema is unsupported")


def save_queue_manifest(manifest: QueueManifest, path: str | None = None) -> None:
    if manifest.schema_version != SCHEMA_VERSION:
        raise QueueManifestStorageError("Only the current manifest schema can be saved")
    manifest_path = path or get_queue_manifest_path()
    _ensure_safe_to_replace(manifest_path)
    manifest_dir = os.path.dirname(manifest_path)
    os.makedirs(manifest_dir, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{MANIFEST_FILENAME}.",
        suffix=".tmp",
        dir=manifest_dir,
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(manifest.as_dict(), handle, indent=2)
            handle.write("\n")
        os.replace(temp_path, manifest_path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
