import os
import tempfile
import types
import unittest

from core.job_history import load_job_history


class JobHistoryCompletionTests(unittest.TestCase):
    def test_completed_job_writes_history_after_output_pdf_exists(self):
        import app

        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = os.path.join(temp_dir, "config", "job_history.json")
            source_pdf = os.path.join(temp_dir, "uploads", "job-123", "My Comic.pdf")
            output_pdf = os.path.join(temp_dir, "output", "job-123", "colorized.pdf")
            os.makedirs(os.path.dirname(source_pdf), exist_ok=True)
            os.makedirs(os.path.dirname(output_pdf), exist_ok=True)
            with open(source_pdf, "wb") as handle:
                handle.write(b"%PDF-1.4\n")
            with open(output_pdf, "wb") as handle:
                handle.write(b"%PDF-1.4\n")

            job = types.SimpleNamespace(
                job_id="job-123",
                pdf_path=source_pdf,
                mode="reference",
                page_count=4,
            )

            wrote_history = app._record_completed_job_history(job, output_pdf, history_path)
            entries = load_job_history(history_path)

        self.assertTrue(wrote_history)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].job_id, "job-123")
        self.assertEqual(entries[0].original_filename, "My Comic.pdf")
        self.assertEqual(entries[0].mode, "reference")
        self.assertEqual(entries[0].output_pdf_path, output_pdf)
        self.assertEqual(entries[0].page_count, 4)
        self.assertIsNone(entries[0].batch_id)
        self.assertTrue(entries[0].completed_at.endswith("Z"))

    def test_completed_batch_job_writes_history_with_batch_id(self):
        import app

        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = os.path.join(temp_dir, "config", "job_history.json")
            source_pdf = os.path.join(temp_dir, "uploads", "job-123", "My Comic.pdf")
            output_pdf = os.path.join(temp_dir, "output", "job-123", "colorized.pdf")
            os.makedirs(os.path.dirname(source_pdf), exist_ok=True)
            os.makedirs(os.path.dirname(output_pdf), exist_ok=True)
            with open(source_pdf, "wb") as handle:
                handle.write(b"%PDF-1.4\n")
            with open(output_pdf, "wb") as handle:
                handle.write(b"%PDF-1.4\n")

            job = types.SimpleNamespace(
                job_id="job-123",
                pdf_path=source_pdf,
                mode="auto",
                page_count=2,
            )

            wrote_history = app._record_completed_job_history(
                job,
                output_pdf,
                history_path,
                batch_id="batch-1",
            )
            entries = load_job_history(history_path)

        self.assertTrue(wrote_history)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].batch_id, "batch-1")

    def test_missing_output_pdf_does_not_write_history(self):
        import app

        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = os.path.join(temp_dir, "config", "job_history.json")
            output_pdf = os.path.join(temp_dir, "output", "job-123", "colorized.pdf")
            job = types.SimpleNamespace(
                job_id="job-123",
                pdf_path=os.path.join(temp_dir, "uploads", "job-123", "comic.pdf"),
                mode="auto",
                page_count=1,
            )

            wrote_history = app._record_completed_job_history(job, output_pdf, history_path)
            entries = load_job_history(history_path)

        self.assertFalse(wrote_history)
        self.assertEqual(entries, [])

    def test_failed_batch_job_without_output_pdf_does_not_write_history(self):
        import app

        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = os.path.join(temp_dir, "config", "job_history.json")
            output_pdf = os.path.join(temp_dir, "output", "job-123", "colorized.pdf")
            job = types.SimpleNamespace(
                job_id="job-123",
                pdf_path=os.path.join(temp_dir, "uploads", "job-123", "comic.pdf"),
                mode="auto",
                page_count=1,
            )

            wrote_history = app._record_completed_job_history(
                job,
                output_pdf,
                history_path,
                batch_id="batch-1",
            )
            entries = load_job_history(history_path)

        self.assertFalse(wrote_history)
        self.assertEqual(entries, [])

    def test_cancelled_batch_job_without_output_pdf_does_not_write_history(self):
        import app

        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = os.path.join(temp_dir, "config", "job_history.json")
            output_pdf = os.path.join(temp_dir, "output", "job-123", "colorized.pdf")
            job = types.SimpleNamespace(
                job_id="job-123",
                pdf_path=os.path.join(temp_dir, "uploads", "job-123", "comic.pdf"),
                mode="auto",
                page_count=1,
                status="cancelled",
            )

            wrote_history = app._record_completed_job_history(
                job,
                output_pdf,
                history_path,
                batch_id="batch-1",
            )
            entries = load_job_history(history_path)

        self.assertFalse(wrote_history)
        self.assertEqual(entries, [])


if __name__ == "__main__":
    unittest.main()
