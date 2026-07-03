import queue
import types
import unittest


class ModelProgressTests(unittest.TestCase):
    def test_auto_model_progress_messages_are_ui_friendly(self):
        import app

        self.assertEqual(
            app._model_progress_message("auto", "Downloading generator weights (~400 MB)..."),
            "Downloading auto colorization model...",
        )
        self.assertEqual(
            app._model_progress_message("auto", "Extracting extractor weights from generator.zip..."),
            "Preparing auto colorization model...",
        )
        self.assertEqual(
            app._model_progress_message("auto", "Downloaded denoiser weights"),
            "Loading auto colorization model...",
        )

    def test_reference_model_progress_messages_are_ui_friendly(self):
        import app

        self.assertEqual(
            app._model_progress_message("reference", "Downloading MangaNinja denoising_unet.pth..."),
            "Downloading MangaNinja weights...",
        )
        self.assertEqual(
            app._model_progress_message("reference", "[MangaNinja] Loading SD 1.5 components..."),
            "Loading SD 1.5 components...",
        )
        self.assertEqual(
            app._model_progress_message("reference", "[MangaNinja] Loading CLIP..."),
            "Loading Reference mode model...",
        )

    def test_model_progress_callback_queues_sse_step_and_updates_job(self):
        import app

        job = types.SimpleNamespace(current_step="")
        events = queue.Queue()
        callback = app._model_progress_callback(job, events, "reference")

        callback("[MangaNinja] Loading SD 1.5 components...")

        self.assertEqual(job.current_step, "Loading SD 1.5 components...")
        self.assertEqual(
            events.get_nowait(),
            {
                "status": "model",
                "step": "Loading SD 1.5 components...",
            },
        )


if __name__ == "__main__":
    unittest.main()
