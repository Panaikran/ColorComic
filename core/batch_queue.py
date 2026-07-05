"""Internal batch queue state helpers for ColorComic."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Mapping


STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

ALLOWED_STATUSES = frozenset(
    {
        STATUS_QUEUED,
        STATUS_RUNNING,
        STATUS_COMPLETED,
        STATUS_FAILED,
        STATUS_CANCELLED,
    }
)
TERMINAL_STATUSES = frozenset(
    {
        STATUS_COMPLETED,
        STATUS_FAILED,
        STATUS_CANCELLED,
    }
)

_JOB_TRANSITIONS = {
    STATUS_QUEUED: frozenset({STATUS_RUNNING, STATUS_CANCELLED}),
    STATUS_RUNNING: frozenset({STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED}),
    STATUS_COMPLETED: frozenset(),
    STATUS_FAILED: frozenset(),
    STATUS_CANCELLED: frozenset(),
}


class BatchQueueError(ValueError):
    """Raised when a batch queue state change is invalid."""


ProcessingCallback = Callable[[str], object]
BatchUpdateCallback = Callable[["BatchRecord"], None]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class BatchCounts:
    queued: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0

    @property
    def total(self) -> int:
        return self.queued + self.running + self.completed + self.failed + self.cancelled


@dataclass(frozen=True)
class BatchRecord:
    batch_id: str
    job_ids: tuple[str, ...]
    job_statuses: Mapping[str, str]
    status: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None

    @property
    def counts(self) -> BatchCounts:
        return count_statuses(self.job_statuses)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


@dataclass(frozen=True)
class BatchRunResult:
    batch: BatchRecord
    processed_job_ids: tuple[str, ...]
    failed_job_ids: tuple[str, ...]


def create_batch(batch_id: str, job_ids: list[str] | tuple[str, ...], now: str | None = None) -> BatchRecord:
    if not batch_id:
        raise BatchQueueError("batch_id is required")

    normalized_job_ids = tuple(job_ids)
    if not normalized_job_ids:
        raise BatchQueueError("At least one job is required")
    if len(set(normalized_job_ids)) != len(normalized_job_ids):
        raise BatchQueueError("Batch job IDs must be unique")

    return BatchRecord(
        batch_id=batch_id,
        job_ids=normalized_job_ids,
        job_statuses={job_id: STATUS_QUEUED for job_id in normalized_job_ids},
        status=STATUS_QUEUED,
        created_at=now or utc_now_iso(),
    )


def count_statuses(job_statuses: Mapping[str, str]) -> BatchCounts:
    counts = {status: 0 for status in ALLOWED_STATUSES}
    for status in job_statuses.values():
        if status not in ALLOWED_STATUSES:
            raise BatchQueueError(f"Unknown job status: {status}")
        counts[status] += 1

    return BatchCounts(
        queued=counts[STATUS_QUEUED],
        running=counts[STATUS_RUNNING],
        completed=counts[STATUS_COMPLETED],
        failed=counts[STATUS_FAILED],
        cancelled=counts[STATUS_CANCELLED],
    )


def can_transition(current_status: str, next_status: str) -> bool:
    if current_status not in ALLOWED_STATUSES:
        raise BatchQueueError(f"Unknown current status: {current_status}")
    if next_status not in ALLOWED_STATUSES:
        raise BatchQueueError(f"Unknown next status: {next_status}")
    if current_status == next_status:
        return True
    return next_status in _JOB_TRANSITIONS[current_status]


def transition_job(batch: BatchRecord, job_id: str, next_status: str, now: str | None = None) -> BatchRecord:
    if job_id not in batch.job_statuses:
        raise BatchQueueError(f"Job is not part of this batch: {job_id}")
    if batch.is_terminal:
        raise BatchQueueError(f"Batch is already terminal: {batch.status}")

    current_status = batch.job_statuses[job_id]
    if not can_transition(current_status, next_status):
        raise BatchQueueError(f"Invalid job transition: {current_status} -> {next_status}")

    if current_status == next_status:
        return batch

    transition_time = now or utc_now_iso()
    updated_statuses = dict(batch.job_statuses)
    updated_statuses[job_id] = next_status

    started_at = batch.started_at
    if started_at is None and next_status == STATUS_RUNNING:
        started_at = transition_time

    new_status = derive_batch_status(updated_statuses, started_at=started_at)
    completed_at = batch.completed_at
    if completed_at is None and new_status in TERMINAL_STATUSES:
        completed_at = transition_time

    return replace(
        batch,
        job_statuses=updated_statuses,
        status=new_status,
        started_at=started_at,
        completed_at=completed_at,
    )


def derive_batch_status(job_statuses: Mapping[str, str], started_at: str | None = None) -> str:
    counts = count_statuses(job_statuses)
    if counts.running > 0:
        return STATUS_RUNNING

    terminal_count = counts.completed + counts.failed + counts.cancelled
    if terminal_count == counts.total:
        if counts.failed > 0:
            return STATUS_FAILED
        if counts.completed > 0:
            return STATUS_COMPLETED
        return STATUS_CANCELLED

    if started_at is not None or terminal_count > 0:
        return STATUS_RUNNING
    return STATUS_QUEUED


def next_queued_job_id(batch: BatchRecord) -> str | None:
    for job_id in batch.job_ids:
        if batch.job_statuses[job_id] == STATUS_QUEUED:
            return job_id
    return None


class SingleWorkerBatchRunner:
    """Run queued batch jobs sequentially with an injected processing callback."""

    def __init__(self, on_update: BatchUpdateCallback | None = None):
        self._started_batch_ids: set[str] = set()
        self.active_job_id: str | None = None
        self._on_update = on_update

    def _emit_update(self, batch: BatchRecord) -> None:
        if self._on_update:
            self._on_update(batch)

    def start(self, batch: BatchRecord, process_job: ProcessingCallback) -> BatchRunResult:
        if batch.batch_id in self._started_batch_ids or batch.started_at is not None:
            raise BatchQueueError(f"Batch has already been started: {batch.batch_id}")
        if batch.status != STATUS_QUEUED:
            raise BatchQueueError(f"Batch cannot be started from status: {batch.status}")

        self._started_batch_ids.add(batch.batch_id)
        return self.run_until_idle(batch, process_job)

    def run_until_idle(self, batch: BatchRecord, process_job: ProcessingCallback) -> BatchRunResult:
        processed_job_ids: list[str] = []
        failed_job_ids: list[str] = []
        current_batch = batch

        while not current_batch.is_terminal:
            job_id = next_queued_job_id(current_batch)
            if job_id is None:
                break

            current_batch = transition_job(current_batch, job_id, STATUS_RUNNING)
            self._emit_update(current_batch)
            self.active_job_id = job_id
            processed_job_ids.append(job_id)
            try:
                result = process_job(job_id)
            except Exception:
                failed_job_ids.append(job_id)
                current_batch = transition_job(current_batch, job_id, STATUS_FAILED)
                self._emit_update(current_batch)
            else:
                if result is False:
                    failed_job_ids.append(job_id)
                    current_batch = transition_job(current_batch, job_id, STATUS_FAILED)
                    self._emit_update(current_batch)
                else:
                    current_batch = transition_job(current_batch, job_id, STATUS_COMPLETED)
                    self._emit_update(current_batch)
            finally:
                self.active_job_id = None

        return BatchRunResult(
            batch=current_batch,
            processed_job_ids=tuple(processed_job_ids),
            failed_job_ids=tuple(failed_job_ids),
        )
