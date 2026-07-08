import os
import unittest


class RecentOutputsUiTests(unittest.TestCase):
    def test_upload_page_contains_recent_outputs_section(self):
        root = os.getcwd()
        with open(os.path.join(root, "templates", "index.html"), encoding="utf-8") as handle:
            template = handle.read()

        self.assertIn('id="recentOutputsSection"', template)
        self.assertIn('id="recentOutputsList"', template)
        self.assertIn('id="recentOutputsEmpty"', template)
        self.assertIn('id="recentOutputsStatus" role="status" aria-live="polite"', template)
        self.assertIn('id="recentOutputsError" role="alert"', template)
        self.assertIn("Recent Outputs", template)

    def test_upload_script_loads_recent_jobs_and_supports_desktop_folder_action(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("fetch('/api/recent-jobs')", script)
        self.assertIn("renderRecentOutput", script)
        self.assertIn("Batch ${job.batch_id}", script)
        self.assertIn("output_pdf_exists", script)
        self.assertIn("output_pdf_safe", script)
        self.assertIn("window.pywebview.api.open_output_folder", script)
        self.assertIn("window.pywebview.api.open_output_pdf", script)
        self.assertIn("Show PDF", script)
        self.assertIn("download.setAttribute('aria-label', `Download ${title.textContent}`)", script)
        self.assertIn("revealPdf.setAttribute('aria-label', `Show PDF for ${title.textContent}`)", script)
        self.assertIn("openFolder.setAttribute('aria-label', `Open output folder for ${title.textContent}`)", script)
        self.assertIn("remove.setAttribute('aria-label', `Remove ${title.textContent} from Recent Outputs`)", script)
        self.assertIn("actionStatus.setAttribute('role', 'status')", script)
        self.assertIn("actionStatus.setAttribute('aria-live', 'polite')", script)
        self.assertIn("/api/download/", script)
        self.assertIn("Remove from list", script)
        self.assertIn("Removes this history entry only. Output files stay on disk.", script)
        self.assertIn("fetch(`/api/recent-jobs/${encodeURIComponent(jobId)}`", script)
        self.assertIn("method: 'DELETE'", script)
        self.assertIn("item.remove()", script)
        self.assertIn("Could not remove this output from the list.", script)

    def test_processing_page_supports_desktop_pdf_reveal_action(self):
        root = os.getcwd()
        with open(os.path.join(root, "templates", "processing.html"), encoding="utf-8") as handle:
            template = handle.read()

        self.assertIn('id="revealOutputPdfBtn"', template)
        self.assertIn("window.pywebview.api.open_output_pdf", template)
        self.assertIn("Show PDF in Folder", template)

    def test_processing_page_surfaces_progress_and_error_state_clearly(self):
        root = os.getcwd()
        with open(os.path.join(root, "templates", "processing.html"), encoding="utf-8") as handle:
            template = handle.read()

        self.assertIn('id="stepText" aria-live="polite"', template)
        self.assertIn('class="progress-info" aria-live="polite"', template)
        self.assertIn('id="errorText" role="alert"', template)
        self.assertIn('alt="Original page preview"', template)
        self.assertIn('alt="Colorized page preview"', template)
        self.assertIn("function showProcessingError(message, step)", template)
        self.assertIn("showProcessingError(data.error, data.step)", template)
        self.assertIn("Completed page ${page + 1} of ${total}", template)
        self.assertIn("Processing was interrupted. Please return to upload and try again.", template)


if __name__ == "__main__":
    unittest.main()
