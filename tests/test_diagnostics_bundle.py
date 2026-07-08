import json
import os
import tempfile
import unittest
import zipfile

from core.diagnostics_bundle import create_diagnostics_bundle


class DiagnosticsBundleTests(unittest.TestCase):
    def test_bundle_includes_diagnostics_manifest_and_small_logs_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = os.path.join(temp_dir, "logs")
            uploads_dir = os.path.join(temp_dir, "uploads")
            output_dir = os.path.join(temp_dir, "output")
            weights_dir = os.path.join(temp_dir, "models", "weights")
            cache_dir = os.path.join(temp_dir, "cache", "huggingface")
            os.makedirs(log_dir)
            for folder in (uploads_dir, output_dir, weights_dir, cache_dir):
                os.makedirs(folder)
                with open(os.path.join(folder, "private.bin"), "wb") as handle:
                    handle.write(b"secret")
            with open(os.path.join(log_dir, "colorcomic.log"), "w", encoding="utf-8") as handle:
                handle.write("small log")
            with open(os.path.join(log_dir, "large.log"), "w", encoding="utf-8") as handle:
                handle.write("too large")

            diagnostics = {
                "paths": {
                    "runtime": {"path": temp_dir},
                    "uploads": {"path": uploads_dir},
                    "output": {"path": output_dir},
                    "weights": {"path": weights_dir},
                    "cache": {"path": cache_dir},
                    "logs": {"path": log_dir},
                }
            }
            bundle_path = create_diagnostics_bundle(
                diagnostics,
                log_dir,
                app_version="test",
                max_log_bytes=16,
            )

            with zipfile.ZipFile(bundle_path) as bundle:
                names = set(bundle.namelist())
                manifest = json.loads(bundle.read("manifest.json").decode("utf-8"))

        self.assertIn("diagnostics.json", names)
        self.assertIn("manifest.json", names)
        self.assertIn("logs/colorcomic.log", names)
        self.assertNotIn("logs/large.log", names)
        self.assertFalse(any(name.startswith("uploads/") for name in names))
        self.assertFalse(any(name.startswith("output/") for name in names))
        self.assertFalse(any(name.startswith("models/") for name in names))
        self.assertFalse(any(name.startswith("cache/") for name in names))
        self.assertEqual(manifest["app"], "ColorComic")
        self.assertEqual(manifest["version"], "test")


if __name__ == "__main__":
    unittest.main()
