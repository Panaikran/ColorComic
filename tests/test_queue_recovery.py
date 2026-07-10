import json
import os
import tempfile
import unittest

import app
from core.batch_queue import (
    STATUS_FAILED,
    STATUS_PAUSED,
    STATUS_QUEUED,
    STATUS_RECOVERY_REQUIRED,
    STATUS_RUNNING,
)
from core.queue_manifest import QueueBatchRecord, QueueJobRecord, QueueManifest, save_queue_manifest


class QueueRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.original_upload_folder = app.Config.UPLOAD_FOLDER
        self.original_config_dir = app.Config.CONFIG_DIR
        app.jobs.clear()
        app.batches.clear()
        app.job_queues.clear()
        app.active_batch_runners.clear()
        self.temp_dir = tempfile.TemporaryDirectory()
        app.Config.UPLOAD_FOLDER = os.path.join(self.temp_dir.name, "uploads")
        app.Config.CONFIG_DIR = os.path.join(self.temp_dir.name, "config")
        os.makedirs(app.Config.UPLOAD_FOLDER)

    def tearDown(self):
        app.Config.UPLOAD_FOLDER = self.original_upload_folder
        app.Config.CONFIG_DIR = self.original_config_dir
        app.jobs.clear()
        app.batches.clear()
        app.job_queues.clear()
        app.active_batch_runners.clear()
        self.temp_dir.cleanup()

    def make_manifest(self, status, source_exists=True, page_exists=True):
        job_dir = os.path.join(app.Config.UPLOAD_FOLDER, "batch-1", "job-1")
        pdf_path = os.path.join(job_dir, "comic.pdf")
        page_path = os.path.join(job_dir, "pages", "page-1.png")
        if source_exists:
            os.makedirs(job_dir, exist_ok=True)
            with open(pdf_path, "wb") as handle:
                handle.write(b"%PDF-1.4\n")
        if page_exists:
            os.makedirs(os.path.dirname(page_path), exist_ok=True)
            with open(page_path, "wb") as handle:
                handle.write(b"PNG")
        job = QueueJobRecord(
            job_id="job-1",
            status=status,
            attempt_number=1,
            pdf_path=pdf_path,
            page_images=(page_path,),
            page_count=1,
            mode="auto",
            style="auto",
            device="cpu",
            error="Prior failure" if status == STATUS_FAILED else None,
        )
        return QueueManifest(batches=(QueueBatchRecord(
            batch_id="batch-1",
            job_ids=("job-1",),
            jobs=(job,),
            created_at="2026-07-10T01:00:00Z",
        ),))

    def save_manifest(self, manifest):
        path = os.path.join(app.Config.CONFIG_DIR, "queue_manifest.json")
        save_queue_manifest(manifest, path)
        return path

    def assert_recovered(self, expected_status):
        batch = app.batches["batch-1"]
        self.assertEqual(batch.job_statuses["job-1"], expected_status)
        self.assertEqual(app.jobs["job-1"].status, expected_status)
        self.assertEqual(app.job_queues, {})
        self.assertEqual(app.active_batch_runners, {})

    def test_queued_job_recovers_without_starting_worker(self):
        path = self.save_manifest(self.make_manifest(STATUS_QUEUED))

        app.restore_queue_manifest(path)

        self.assert_recovered(STATUS_QUEUED)

    def test_paused_job_recovers_as_paused(self):
        path = self.save_manifest(self.make_manifest(STATUS_PAUSED))

        app.restore_queue_manifest(path)

        self.assert_recovered(STATUS_PAUSED)

    def test_failed_job_recovers_as_failed_and_retryable(self):
        path = self.save_manifest(self.make_manifest(STATUS_FAILED))

        app.restore_queue_manifest(path)

        self.assert_recovered(STATUS_FAILED)
        self.assertEqual(app.jobs["job-1"].error, "Prior failure")

    def test_interrupted_running_job_requires_recovery(self):
        path = self.save_manifest(self.make_manifest(STATUS_RUNNING))

        app.restore_queue_manifest(path)

        self.assert_recovered(STATUS_RECOVERY_REQUIRED)
        self.assertIn("interrupted", app.jobs["job-1"].error.lower())

    def test_missing_source_pdf_requires_recovery(self):
        path = self.save_manifest(self.make_manifest(STATUS_QUEUED, source_exists=False))

        app.restore_queue_manifest(path)

        self.assert_recovered(STATUS_RECOVERY_REQUIRED)
        self.assertIn("source pdf", app.jobs["job-1"].error.lower())

    def test_missing_extracted_page_requires_recovery(self):
        path = self.save_manifest(self.make_manifest(STATUS_PAUSED, page_exists=False))

        app.restore_queue_manifest(path)

        self.assert_recovered(STATUS_RECOVERY_REQUIRED)
        self.assertIn("extracted page", app.jobs["job-1"].error)

    def test_corrupt_manifest_recovers_nothing(self):
        path = os.path.join(app.Config.CONFIG_DIR, "queue_manifest.json")
        os.makedirs(app.Config.CONFIG_DIR)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not json")

        self.assertEqual(app.restore_queue_manifest(path), 0)
        self.assertEqual(app.jobs, {})
        self.assertEqual(app.batches, {})

    def test_unsupported_manifest_schema_recovers_nothing(self):
        path = os.path.join(app.Config.CONFIG_DIR, "queue_manifest.json")
        os.makedirs(app.Config.CONFIG_DIR)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"schema_version": 2, "batches": []}, handle)

        self.assertEqual(app.restore_queue_manifest(path), 0)
        self.assertEqual(app.jobs, {})
        self.assertEqual(app.batches, {})

    def test_startup_with_no_manifest_is_idempotent(self):
        app.create_app()
        app.create_app()

        self.assertEqual(app.jobs, {})
        self.assertEqual(app.batches, {})
        self.assertEqual(app.job_queues, {})
        self.assertEqual(app.active_batch_runners, {})

    def test_startup_restores_manifest_idempotently_without_starting_workers(self):
        self.save_manifest(self.make_manifest(STATUS_QUEUED))

        app.create_app()
        app.create_app()

        self.assert_recovered(STATUS_QUEUED)
        self.assertEqual(len(app.batches), 1)


if __name__ == "__main__":
    unittest.main()
