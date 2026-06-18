import unittest


class ReferenceModeErrorTests(unittest.TestCase):
    def test_unreadable_reference_image_reports_reference_preprocessing_step(self):
        import app

        class FakeCv2:
            @staticmethod
            def imread(path):
                return None

        with self.assertRaises(app.ColorizationStepError) as caught:
            app._read_image_or_raise(
                "missing-reference.png",
                "reference preprocessing",
                "reference",
                cv2_module=FakeCv2,
            )

        self.assertEqual(caught.exception.step, "reference preprocessing")
        self.assertIn(
            "reference preprocessing failed: OpenCV could not read reference image",
            app._step_error_message(caught.exception, "fallback"),
        )


if __name__ == "__main__":
    unittest.main()
