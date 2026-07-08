import importlib
import os
import queue
import sys
import tempfile
import types
import unittest


class FakeInferenceMode:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeColorizer:
    def colorize(self, image):
        return image


class FakeModelManager:
    def switch_device(self, device):
        self.device = device

    def get_colorizer(self, mode, callback=None):
        return FakeColorizer()


class FakePostProcessor:
    def process(self, result, image):
        return result


class FakeConsistency:
    def set_reference(self, result):
        self.reference = result

    def apply(self, result, strength):
        return result


class ColorizationTimingTests(unittest.TestCase):
    def setUp(self):
        self.original_modules = {}
        for name in ("cv2", "torch", "core.color_consistency", "core.pdf_handler"):
            self.original_modules[name] = sys.modules.get(name)

        fake_cv2 = types.ModuleType("cv2")
        fake_cv2.IMWRITE_JPEG_QUALITY = 1
        fake_cv2.imread = lambda path: b"image"
        fake_cv2.imwrite = lambda path, result, options=None: True
        sys.modules["cv2"] = fake_cv2

        fake_torch = types.ModuleType("torch")
        fake_torch.inference_mode = lambda: FakeInferenceMode()
        sys.modules["torch"] = fake_torch

        fake_consistency = types.ModuleType("core.color_consistency")
        fake_consistency.ColorConsistencyManager = FakeConsistency
        sys.modules["core.color_consistency"] = fake_consistency

        fake_pdf = types.ModuleType("core.pdf_handler")
        fake_pdf.reassemble_pdf = self.reassemble_pdf
        sys.modules["core.pdf_handler"] = fake_pdf

        self.app = importlib.import_module("app")
        self.original_get_model_manager = self.app.get_model_manager
        self.original_get_post_processor = self.app.get_post_processor
        self.original_record_history = self.app._record_completed_job_history
        self.app.get_model_manager = lambda: FakeModelManager()
        self.app.get_post_processor = lambda: FakePostProcessor()
        self.app._record_completed_job_history = lambda job, output_pdf, batch_id=None: True

    def tearDown(self):
        self.app.get_model_manager = self.original_get_model_manager
        self.app.get_post_processor = self.original_get_post_processor
        self.app._record_completed_job_history = self.original_record_history
        for name, module in self.original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def reassemble_pdf(self, colored_paths, output_pdf, source_pdf):
        with open(output_pdf, "wb") as handle:
            handle.write(b"%PDF-1.4\n")

    def make_job(self, pdf_path, page_images):
        return types.SimpleNamespace(
            job_id="job-1",
            pdf_path=pdf_path,
            page_count=len(page_images),
            page_images=page_images,
            colorized_images=[],
            output_pdf=None,
            status="colorizing",
            progress=0.0,
            current_step="",
            timing_summary=None,
            style="auto",
            device="cpu",
            mode="auto",
            reference_image_path=None,
        )

    def drain_events(self, events):
        drained = []
        while not events.empty():
            drained.append(events.get())
        return drained

    def test_worker_records_timing_without_changing_sse_event_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = os.path.join(temp_dir, "input.pdf")
            page_path = os.path.join(temp_dir, "page.png")
            out_dir = os.path.join(temp_dir, "out")
            os.makedirs(out_dir)
            open(pdf_path, "wb").close()
            open(page_path, "wb").close()
            job = self.make_job(pdf_path, [page_path])
            events = queue.Queue()

            result = self.app._run_colorization_job("job-1", job, events, out_dir)

        self.assertTrue(result)
        self.assertEqual(job.status, "done")
        self.assertEqual(
            [step["name"] for step in job.timing_summary["steps"]],
            ["model_load", "page_colorization", "pdf_export", "history_record"],
        )
        event_keys = [set(event.keys()) for event in self.drain_events(events)]
        self.assertEqual(event_keys[-1], {"done", "download_url"})
        self.assertNotIn("timing_summary", event_keys[-1])

    def test_worker_stores_partial_timing_on_failure(self):
        def fail_history(job, output_pdf, batch_id=None):
            raise RuntimeError("history failed")

        self.app._record_completed_job_history = fail_history
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = os.path.join(temp_dir, "input.pdf")
            page_path = os.path.join(temp_dir, "page.png")
            out_dir = os.path.join(temp_dir, "out")
            os.makedirs(out_dir)
            open(pdf_path, "wb").close()
            open(page_path, "wb").close()
            job = self.make_job(pdf_path, [page_path])

            result = self.app._run_colorization_job("job-1", job, queue.Queue(), out_dir)

        self.assertFalse(result)
        self.assertEqual(job.status, "error")
        self.assertEqual(job.timing_summary["steps"][-1]["name"], "history_record")
        self.assertEqual(job.timing_summary["steps"][-1]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
