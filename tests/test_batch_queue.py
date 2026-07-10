import unittest

from core.batch_queue import (
    BatchQueueError,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PAUSED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    SingleWorkerBatchRunner,
    create_batch,
    remove_queued_job,
    reorder_queued_job,
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

    def test_queued_job_can_be_paused_and_resumed_without_starting_batch(self):
        batch = create_batch("batch-1", ["job-1", "job-2"])

        batch = transition_job(batch, "job-1", STATUS_PAUSED)

        self.assertEqual(batch.job_statuses["job-1"], STATUS_PAUSED)
        self.assertEqual(batch.status, STATUS_QUEUED)
        self.assertIsNone(batch.started_at)
        self.assertEqual(batch.counts.queued, 1)
        self.assertEqual(batch.counts.paused, 1)

        batch = transition_job(batch, "job-1", STATUS_QUEUED)

        self.assertEqual(batch.job_statuses["job-1"], STATUS_QUEUED)
        self.assertEqual(batch.counts.queued, 2)
        self.assertEqual(batch.counts.paused, 0)

    def test_paused_job_cannot_transition_directly_to_running(self):
        batch = create_batch("batch-1", ["job-1"])
        batch = transition_job(batch, "job-1", STATUS_PAUSED)

        with self.assertRaises(BatchQueueError):
            transition_job(batch, "job-1", STATUS_RUNNING)

    def test_reorder_moves_only_queued_jobs_and_keeps_other_job_positions(self):
        batch = create_batch("batch-1", ["job-1", "job-2", "job-3", "job-4"])
        batch = transition_job(batch, "job-2", STATUS_PAUSED)
        batch = transition_job(batch, "job-3", STATUS_CANCELLED)

        reordered = reorder_queued_job(batch, "job-4", "job-1")

        self.assertEqual(reordered.job_ids, ("job-4", "job-2", "job-3", "job-1"))
        self.assertEqual(reordered.job_statuses, batch.job_statuses)

    def test_reorder_rejects_non_queued_source_or_target(self):
        batch = create_batch("batch-1", ["job-1", "job-2", "job-3"])
        batch = transition_job(batch, "job-2", STATUS_PAUSED)

        with self.assertRaises(BatchQueueError):
            reorder_queued_job(batch, "job-2", "job-1")
        with self.assertRaises(BatchQueueError):
            reorder_queued_job(batch, "job-1", "job-2")

    def test_remove_queued_job_drops_it_from_active_queue_state(self):
        batch = create_batch("batch-1", ["job-1", "job-2"])

        updated = remove_queued_job(batch, "job-1")

        self.assertEqual(updated.job_ids, ("job-2",))
        self.assertNotIn("job-1", updated.job_statuses)
        self.assertEqual(updated.counts.total, 1)
        self.assertEqual(updated.status, STATUS_QUEUED)

    def test_remove_rejects_non_queued_jobs_and_marks_empty_batch_cancelled(self):
        batch = create_batch("batch-1", ["job-1", "job-2"])
        paused = transition_job(batch, "job-1", STATUS_PAUSED)

        with self.assertRaises(BatchQueueError):
            remove_queued_job(paused, "job-1")

        remaining = remove_queued_job(batch, "job-1")
        empty = remove_queued_job(remaining, "job-2", now="2026-07-10T01:00:00Z")

        self.assertEqual(empty.job_ids, ())
        self.assertEqual(empty.job_statuses, {})
        self.assertEqual(empty.status, STATUS_CANCELLED)
        self.assertEqual(empty.completed_at, "2026-07-10T01:00:00Z")

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

    def test_single_worker_processes_jobs_sequentially(self):
        batch = create_batch("batch-1", ["job-1", "job-2", "job-3"])
        runner = SingleWorkerBatchRunner()
        order = []
        active_seen = []

        def process(job_id):
            order.append(job_id)
            active_seen.append(runner.active_job_id)
            return True

        result = runner.start(batch, process)

        self.assertEqual(order, ["job-1", "job-2", "job-3"])
        self.assertEqual(active_seen, ["job-1", "job-2", "job-3"])
        self.assertEqual(result.processed_job_ids, ("job-1", "job-2", "job-3"))
        self.assertEqual(result.failed_job_ids, ())
        self.assertEqual(result.batch.status, STATUS_COMPLETED)
        self.assertEqual(result.batch.counts.completed, 3)
        self.assertIsNone(runner.active_job_id)

    def test_single_worker_continues_after_job_failure(self):
        batch = create_batch("batch-1", ["job-1", "job-2", "job-3"])
        runner = SingleWorkerBatchRunner()
        order = []

        def process(job_id):
            order.append(job_id)
            if job_id == "job-2":
                raise RuntimeError("job failed")
            return True

        result = runner.start(batch, process)

        self.assertEqual(order, ["job-1", "job-2", "job-3"])
        self.assertEqual(result.processed_job_ids, ("job-1", "job-2", "job-3"))
        self.assertEqual(result.failed_job_ids, ("job-2",))
        self.assertEqual(result.batch.job_statuses["job-1"], STATUS_COMPLETED)
        self.assertEqual(result.batch.job_statuses["job-2"], STATUS_FAILED)
        self.assertEqual(result.batch.job_statuses["job-3"], STATUS_COMPLETED)
        self.assertEqual(result.batch.status, STATUS_FAILED)
        self.assertTrue(result.batch.is_terminal)

    def test_single_worker_marks_false_callback_result_failed(self):
        batch = create_batch("batch-1", ["job-1", "job-2"])
        runner = SingleWorkerBatchRunner()

        def process(job_id):
            return job_id != "job-1"

        result = runner.start(batch, process)

        self.assertEqual(result.failed_job_ids, ("job-1",))
        self.assertEqual(result.batch.job_statuses["job-1"], STATUS_FAILED)
        self.assertEqual(result.batch.job_statuses["job-2"], STATUS_COMPLETED)
        self.assertEqual(result.batch.status, STATUS_FAILED)

    def test_single_worker_rejects_duplicate_start(self):
        batch = create_batch("batch-1", ["job-1"])
        runner = SingleWorkerBatchRunner()
        result = runner.start(batch, lambda job_id: True)

        with self.assertRaises(BatchQueueError):
            runner.start(batch, lambda job_id: True)
        with self.assertRaises(BatchQueueError):
            runner.start(result.batch, lambda job_id: True)

    def test_single_worker_idle_when_no_queued_jobs_remain(self):
        batch = create_batch("batch-1", ["job-1"])
        batch = transition_job(batch, "job-1", STATUS_RUNNING)
        runner = SingleWorkerBatchRunner()
        called = []

        result = runner.run_until_idle(batch, lambda job_id: called.append(job_id))

        self.assertEqual(called, [])
        self.assertEqual(result.processed_job_ids, ())
        self.assertEqual(result.failed_job_ids, ())
        self.assertEqual(result.batch, batch)

    def test_single_worker_preserves_external_queued_cancellation(self):
        current_batch = create_batch("batch-1", ["job-1", "job-2"])
        seen = []

        def store_update(batch):
            nonlocal current_batch
            current_batch = batch

        def get_latest(batch_id):
            return current_batch if batch_id == current_batch.batch_id else None

        runner = SingleWorkerBatchRunner(on_update=store_update, get_latest=get_latest)

        def process(job_id):
            nonlocal current_batch
            seen.append(job_id)
            if job_id == "job-1":
                current_batch = transition_job(current_batch, "job-2", STATUS_CANCELLED)
            return True

        result = runner.start(current_batch, process)

        self.assertEqual(seen, ["job-1"])
        self.assertEqual(result.batch.job_statuses["job-1"], STATUS_COMPLETED)
        self.assertEqual(result.batch.job_statuses["job-2"], STATUS_CANCELLED)
        self.assertEqual(result.batch.counts.completed, 1)
        self.assertEqual(result.batch.counts.cancelled, 1)
        self.assertEqual(result.batch.status, STATUS_COMPLETED)


if __name__ == "__main__":
    unittest.main()
