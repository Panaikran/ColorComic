import unittest

from core.batch_queue import (
    BatchQueueError,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    create_batch,
    transition_job,
)


class BatchQueueTests(unittest.TestCase):
    def test_create_batch_initializes_jobs_and_timestamps(self):
        batch = create_batch("batch-1", ["job-1", "job-2"], now="2026-07-05T01:00:00Z")

        self.assertEqual(batch.batch_id, "batch-1")
        self.assertEqual(batch.job_ids, ("job-1", "job-2"))
        self.assertEqual(batch.status, STATUS_QUEUED)
        self.assertEqual(batch.created_at, "2026-07-05T01:00:00Z")
        self.assertIsNone(batch.started_at)
        self.assertIsNone(batch.completed_at)
        self.assertEqual(batch.job_statuses["job-1"], STATUS_QUEUED)
        self.assertEqual(batch.job_statuses["job-2"], STATUS_QUEUED)

    def test_create_batch_rejects_missing_or_duplicate_identifiers(self):
        with self.assertRaises(BatchQueueError):
            create_batch("", ["job-1"])
        with self.assertRaises(BatchQueueError):
            create_batch("batch-1", [])
        with self.assertRaises(BatchQueueError):
            create_batch("batch-1", ["job-1", "job-1"])

    def test_status_counts_track_all_allowed_statuses(self):
        batch = create_batch("batch-1", ["job-1", "job-2", "job-3", "job-4"])
        batch = transition_job(batch, "job-1", STATUS_RUNNING, now="2026-07-05T01:01:00Z")
        batch = transition_job(batch, "job-1", STATUS_COMPLETED, now="2026-07-05T01:02:00Z")
        batch = transition_job(batch, "job-2", STATUS_RUNNING, now="2026-07-05T01:03:00Z")
        batch = transition_job(batch, "job-2", STATUS_FAILED, now="2026-07-05T01:04:00Z")
        batch = transition_job(batch, "job-3", STATUS_CANCELLED, now="2026-07-05T01:05:00Z")

        self.assertEqual(batch.counts.queued, 1)
        self.assertEqual(batch.counts.running, 0)
        self.assertEqual(batch.counts.completed, 1)
        self.assertEqual(batch.counts.failed, 1)
        self.assertEqual(batch.counts.cancelled, 1)
        self.assertEqual(batch.counts.total, 4)
        self.assertEqual(batch.status, STATUS_RUNNING)

    def test_valid_state_transitions_set_batch_timestamps(self):
        batch = create_batch("batch-1", ["job-1"], now="2026-07-05T01:00:00Z")
        batch = transition_job(batch, "job-1", STATUS_RUNNING, now="2026-07-05T01:01:00Z")

        self.assertEqual(batch.status, STATUS_RUNNING)
        self.assertEqual(batch.started_at, "2026-07-05T01:01:00Z")
        self.assertIsNone(batch.completed_at)

        batch = transition_job(batch, "job-1", STATUS_COMPLETED, now="2026-07-05T01:02:00Z")

        self.assertEqual(batch.status, STATUS_COMPLETED)
        self.assertEqual(batch.completed_at, "2026-07-05T01:02:00Z")
        self.assertTrue(batch.is_terminal)

    def test_invalid_transition_is_rejected(self):
        batch = create_batch("batch-1", ["job-1"])

        with self.assertRaises(BatchQueueError):
            transition_job(batch, "job-1", STATUS_COMPLETED)

        with self.assertRaises(BatchQueueError):
            transition_job(batch, "missing-job", STATUS_RUNNING)

    def test_terminal_batch_rejects_further_transitions(self):
        batch = create_batch("batch-1", ["job-1"])
        batch = transition_job(batch, "job-1", STATUS_RUNNING, now="2026-07-05T01:01:00Z")
        batch = transition_job(batch, "job-1", STATUS_FAILED, now="2026-07-05T01:02:00Z")

        self.assertEqual(batch.status, STATUS_FAILED)
        self.assertTrue(batch.is_terminal)
        with self.assertRaises(BatchQueueError):
            transition_job(batch, "job-1", STATUS_CANCELLED)

    def test_all_cancelled_batch_becomes_cancelled_terminal(self):
        batch = create_batch("batch-1", ["job-1", "job-2"])
        batch = transition_job(batch, "job-1", STATUS_CANCELLED, now="2026-07-05T01:01:00Z")
        batch = transition_job(batch, "job-2", STATUS_CANCELLED, now="2026-07-05T01:02:00Z")

        self.assertEqual(batch.status, STATUS_CANCELLED)
        self.assertEqual(batch.completed_at, "2026-07-05T01:02:00Z")
        self.assertTrue(batch.is_terminal)


if __name__ == "__main__":
    unittest.main()
