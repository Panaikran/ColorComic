import os
import tempfile
import unittest

from core.preflight import validate_colorize_preflight


class PreflightTests(unittest.TestCase):
    def test_valid_pdf_and_output_path_pass(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = os.path.join(temp_dir, "input.pdf")
            output_folder = os.path.join(temp_dir, "output")
            with open(pdf_path, "wb") as handle:
                handle.write(b"%PDF-1.4\n")

            result = validate_colorize_preflight(
                pdf_path,
                "job-123",
                output_folder,
                page_count_reader=lambda path: 2,
            )

            self.assertTrue(result.ok)
            self.assertEqual(result.page_count, 2)
            self.assertEqual(result.errors, ())
            self.assertEqual(result.output_dir, os.path.join(output_folder, "job-123"))
            self.assertTrue(os.path.isdir(result.output_dir))

    def test_missing_pdf_returns_structured_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = validate_colorize_preflight(
                os.path.join(temp_dir, "missing.pdf"),
                "job-123",
                os.path.join(temp_dir, "output"),
                page_count_reader=lambda path: 1,
            )

            self.assertFalse(result.ok)
            self.assertEqual(result.errors[0].code, "pdf_missing")
            self.assertEqual(result.errors[0].step, "PDF preflight")

    def test_unopenable_pdf_returns_structured_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = os.path.join(temp_dir, "broken.pdf")
            output_folder = os.path.join(temp_dir, "output")
            with open(pdf_path, "wb") as handle:
                handle.write(b"not a pdf")

            result = validate_colorize_preflight(
                pdf_path,
                "job-123",
                output_folder,
                page_count_reader=lambda path: (_ for _ in ()).throw(ValueError("bad pdf")),
            )

            self.assertFalse(result.ok)
            self.assertEqual(result.errors[0].code, "pdf_unreadable")
            self.assertIn("bad pdf", result.errors[0].message)

    def test_zero_page_pdf_returns_structured_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = os.path.join(temp_dir, "empty.pdf")
            with open(pdf_path, "wb") as handle:
                handle.write(b"%PDF-1.4\n")

            result = validate_colorize_preflight(
                pdf_path,
                "job-123",
                os.path.join(temp_dir, "output"),
                page_count_reader=lambda path: 0,
            )

            self.assertFalse(result.ok)
            self.assertEqual(result.errors[0].code, "pdf_has_no_pages")

    def test_output_job_dir_cannot_escape_output_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = os.path.join(temp_dir, "input.pdf")
            with open(pdf_path, "wb") as handle:
                handle.write(b"%PDF-1.4\n")

            result = validate_colorize_preflight(
                pdf_path,
                "..",
                os.path.join(temp_dir, "output"),
                page_count_reader=lambda path: 1,
            )

            self.assertFalse(result.ok)
            self.assertIsNone(result.output_dir)
            self.assertEqual(result.errors[0].code, "output_path_invalid")

    def test_result_can_be_serialized_for_future_sse_or_ui_use(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = validate_colorize_preflight(
                os.path.join(temp_dir, "missing.pdf"),
                "job-123",
                os.path.join(temp_dir, "output"),
                page_count_reader=lambda path: 1,
            )

            payload = result.as_dict()

            self.assertEqual(payload["ok"], False)
            self.assertEqual(payload["errors"][0]["code"], "pdf_missing")
            self.assertEqual(payload["errors"][0]["step"], "PDF preflight")


if __name__ == "__main__":
    unittest.main()
