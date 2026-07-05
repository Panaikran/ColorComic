import json
import os
import tempfile
import unittest

from core.job_history import (
    HISTORY_FILENAME,
    JobHistoryEntry,
    append_job_history,
    get_history_path,
    load_job_history,
    save_job_history,
)


class JobHistoryTests(unittest.TestCase):
    def make_entry(self, job_id="job-1", page_count=3, batch_id=None):
        return JobHistoryEntry(
            job_id=job_id,
            original_filename="comic.pdf",
            mode="auto",
            completed_at="2026-07-03T12:00:00Z",
            output_pdf_path=r"C:\Users\User\AppData\Local\ColorComic\output\job-1\colorized.pdf",
            page_count=page_count,
            batch_id=batch_id,
        )

    def test_history_path_uses_config_dir(self):
        self.assertEqual(
            get_history_path(r"C:\Runtime\Config"),
            os.path.join(r"C:\Runtime\Config", HISTORY_FILENAME),
        )

    def test_missing_history_file_loads_empty_list(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            entries = load_job_history(os.path.join(temp_dir, HISTORY_FILENAME))

        self.assertEqual(entries, [])

    def test_corrupt_history_file_loads_empty_list(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, HISTORY_FILENAME)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{not valid json")

            entries = load_job_history(path)

        self.assertEqual(entries, [])

    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "nested", HISTORY_FILENAME)
            entry = self.make_entry()

            save_job_history([entry], path)
            entries = load_job_history(path)

        self.assertEqual(entries, [entry])

    def test_invalid_history_entries_are_skipped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, HISTORY_FILENAME)
            valid = self.make_entry().as_dict()
            with open(path, "w", encoding="utf-8") as handle:
                json.dump([{"job_id": ""}, valid, "bad"], handle)

            entries = load_job_history(path)

        self.assertEqual(entries, [self.make_entry()])

    def test_append_history_replaces_duplicate_and_enforces_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, HISTORY_FILENAME)
            old_job = self.make_entry("old-job", page_count=1)
            duplicate = self.make_entry("job-1", page_count=2)
            updated = self.make_entry("job-1", page_count=5)
            save_job_history([old_job, duplicate], path)

            entries = append_job_history(updated, path, limit=2)
            loaded_entries = load_job_history(path)

        self.assertEqual(entries, [updated, old_job])
        self.assertEqual(loaded_entries, [updated, old_job])

    def test_page_count_is_optional(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, HISTORY_FILENAME)
            entry = self.make_entry(page_count=None)

            save_job_history([entry], path)
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            entries = load_job_history(path)

        self.assertNotIn("page_count", payload[0])
        self.assertEqual(entries, [entry])

    def test_batch_id_is_optional_and_omitted_when_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, HISTORY_FILENAME)
            entry = self.make_entry(batch_id=None)

            save_job_history([entry], path)
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            entries = load_job_history(path)

        self.assertNotIn("batch_id", payload[0])
        self.assertIsNone(entries[0].batch_id)
        self.assertEqual(entries, [entry])

    def test_batch_id_round_trips_when_present(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, HISTORY_FILENAME)
            entry = self.make_entry(batch_id="batch-1")

            save_job_history([entry], path)
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            entries = load_job_history(path)

        self.assertEqual(payload[0]["batch_id"], "batch-1")
        self.assertEqual(entries, [entry])

    def test_existing_history_without_batch_id_still_loads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, HISTORY_FILENAME)
            legacy_payload = self.make_entry().as_dict()
            legacy_payload.pop("batch_id", None)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump([legacy_payload], handle)

            entries = load_job_history(path)

        self.assertEqual(len(entries), 1)
        self.assertIsNone(entries[0].batch_id)


if __name__ == "__main__":
    unittest.main()
