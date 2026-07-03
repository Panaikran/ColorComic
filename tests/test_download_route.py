import os
import tempfile
import unittest


class DownloadRouteTests(unittest.TestCase):
    def test_download_route_serves_pdf_from_runtime_output_directory(self):
        import app

        original_output_folder = app.Config.OUTPUT_FOLDER
        job_id = "runtime-job"

        with tempfile.TemporaryDirectory() as temp_dir:
            output_folder = os.path.join(temp_dir, "output")
            pdf_dir = os.path.join(output_folder, job_id)
            pdf_path = os.path.join(pdf_dir, "colorized.pdf")
            os.makedirs(pdf_dir, exist_ok=True)
            with open(pdf_path, "wb") as handle:
                handle.write(b"%PDF-1.4\n% test\n")

            app.Config.OUTPUT_FOLDER = output_folder
            app.jobs.clear()
            flask_app = app.create_app()
            flask_app.config["TESTING"] = True

            try:
                response = flask_app.test_client().get(f"/api/download/{job_id}")
                response_body = response.data
                response_headers = dict(response.headers)
                response_status = response.status_code
                response.close()
            finally:
                app.Config.OUTPUT_FOLDER = original_output_folder
                app.jobs.clear()

        self.assertEqual(response_status, 200)
        self.assertEqual(response_body, b"%PDF-1.4\n% test\n")
        self.assertIn(
            "attachment; filename=colorized.pdf",
            response_headers["Content-Disposition"],
        )


if __name__ == "__main__":
    unittest.main()
