import os
import tempfile
import unittest

from core.runtime_cleanup import cleanup_orphaned_uploads


class RuntimeCleanupTests(unittest.TestCase):
    def touch_old(self, path, now):
        os.utime(path, (now - 90000, now - 90000))

    def test_orphaned_temp_upload_directory_is_removed(self):
        now = 100000.0
        with tempfile.TemporaryDirectory() as temp_dir:
            uploads = os.path.join(temp_dir, "uploads")
            orphan = os.path.join(uploads, "orphan-job")
            os.makedirs(orphan)
            self.touch_old(orphan, now)

            result = cleanup_orphaned_uploads(uploads, now=now)
            self.assertFalse(os.path.exists(orphan))

        self.assertEqual(len(result.removed), 1)
        self.assertEqual(result.errors, ())

    def test_active_upload_paths_are_preserved(self):
        now = 100000.0
        with tempfile.TemporaryDirectory() as temp_dir:
            uploads = os.path.join(temp_dir, "uploads")
            active_job = os.path.join(uploads, "active-job")
            active_pdf = os.path.join(active_job, "input.pdf")
            os.makedirs(active_job)
            with open(active_pdf, "wb") as handle:
                handle.write(b"%PDF-1.4\n")
            self.touch_old(active_job, now)

            result = cleanup_orphaned_uploads(uploads, active_paths=[active_pdf], now=now)

            self.assertEqual(result.removed, ())
            self.assertTrue(os.path.exists(active_pdf))

    def test_output_directory_is_not_considered_for_cleanup(self):
        now = 100000.0
        with tempfile.TemporaryDirectory() as temp_dir:
            uploads = os.path.join(temp_dir, "uploads")
            output = os.path.join(temp_dir, "output", "job-1")
            output_pdf = os.path.join(output, "colorized.pdf")
            os.makedirs(uploads)
            os.makedirs(output)
            with open(output_pdf, "wb") as handle:
                handle.write(b"%PDF-1.4\n")
            self.touch_old(output, now)

            result = cleanup_orphaned_uploads(uploads, now=now)

            self.assertEqual(result.removed, ())
            self.assertTrue(os.path.exists(output_pdf))

    def test_history_file_is_preserved(self):
        now = 100000.0
        with tempfile.TemporaryDirectory() as temp_dir:
            uploads = os.path.join(temp_dir, "uploads")
            config = os.path.join(temp_dir, "config")
            history = os.path.join(config, "job_history.json")
            os.makedirs(uploads)
            os.makedirs(config)
            with open(history, "w", encoding="utf-8") as handle:
                handle.write("[]")
            self.touch_old(config, now)

            result = cleanup_orphaned_uploads(uploads, now=now)

            self.assertEqual(result.removed, ())
            self.assertTrue(os.path.exists(history))


if __name__ == "__main__":
    unittest.main()
