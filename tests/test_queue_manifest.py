import json
import os
import tempfile
import unittest
from unittest import mock

from core.queue_manifest import (
    QueueBatchRecord,
    QueueJobRecord,
    QueueManifest,
    QueueManifestStorageError,
    get_queue_manifest_path,
    load_queue_manifest,
    save_queue_manifest,
)


class QueueManifestTests(unittest.TestCase):
    def make_manifest(self):
        job = QueueJobRecord(
            job_id="job-2",
            status="paused",
            attempt_number=2,
            pdf_path=r"C:\Runtime\uploads\batch-1\comic.pdf",
            page_images=(r"C:\Runtime\uploads\batch-1\page-1.png",),
            page_count=1,
            mode="auto",
            style="auto",
            device="cpu",
            retry_of_job_id="job-1",
            error="Previous attempt failed",
        )
        batch = QueueBatchRecord(
            batch_id="batch-1",
            job_ids=("job-2",),
            jobs=(job,),
            created_at="2026-07-10T01:00:00Z",
        )
        return QueueManifest(batches=(batch,))

    def test_manifest_path_uses_config_directory(self):
        self.assertEqual(
            get_queue_manifest_path(r"C:\Runtime\config"),
            os.path.join(r"C:\Runtime\config", "queue_manifest.json"),
        )

    def test_save_and_load_round_trip_reconstructable_metadata_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "queue_manifest.json")
            manifest = self.make_manifest()

            save_queue_manifest(manifest, path)
            loaded = load_queue_manifest(path)

            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)

        self.assertEqual(loaded, manifest)
        self.assertEqual(payload["schema_version"], 1)
        self.assertNotIn("output_pdf", payload["batches"][0]["jobs"][0])
        self.assertNotIn("colorized_images", payload["batches"][0]["jobs"][0])

    def test_missing_manifest_loads_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = load_queue_manifest(os.path.join(temp_dir, "missing.json"))

        self.assertIsNone(manifest)

    def test_malformed_manifest_loads_none_and_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "queue_manifest.json")
            malformed = "{not json"
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(malformed)

            self.assertIsNone(load_queue_manifest(path))
            with self.assertRaises(QueueManifestStorageError):
                save_queue_manifest(self.make_manifest(), path)

            with open(path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), malformed)

    def test_unknown_fields_are_ignored(self):
        payload = self.make_manifest().as_dict()
        payload["future_top_level"] = "ignored"
        payload["batches"][0]["future_batch_field"] = "ignored"
        payload["batches"][0]["jobs"][0]["future_job_field"] = "ignored"

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "queue_manifest.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)

            loaded = load_queue_manifest(path)

        self.assertEqual(loaded, self.make_manifest())

    def test_unsupported_future_schema_loads_none_and_is_not_overwritten(self):
        payload = {"schema_version": 2, "batches": []}

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "queue_manifest.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)

            self.assertIsNone(load_queue_manifest(path))
            with self.assertRaises(QueueManifestStorageError):
                save_queue_manifest(self.make_manifest(), path)

            with open(path, "r", encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), payload)

    def test_load_runs_registered_migration_hook(self):
        legacy_payload = {"schema_version": 0, "legacy": True}
        migrated_payload = self.make_manifest().as_dict()

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "queue_manifest.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(legacy_payload, handle)

            with mock.patch.dict(
                "core.queue_manifest.MIGRATORS",
                {0: lambda payload: migrated_payload},
                clear=True,
            ):
                loaded = load_queue_manifest(path)

        self.assertEqual(loaded, self.make_manifest())

    def test_save_uses_replace_after_writing_temporary_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "queue_manifest.json")
            with mock.patch("core.queue_manifest.os.replace", wraps=os.replace) as replace:
                save_queue_manifest(self.make_manifest(), path)

            self.assertEqual(replace.call_count, 1)
            self.assertEqual(replace.call_args.args[1], path)
            self.assertEqual(load_queue_manifest(path), self.make_manifest())
            self.assertEqual(
                [name for name in os.listdir(temp_dir) if name.endswith(".tmp")],
                [],
            )


if __name__ == "__main__":
    unittest.main()
