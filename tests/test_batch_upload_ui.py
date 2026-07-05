import os
import unittest


class BatchUploadUiTests(unittest.TestCase):
    def test_upload_page_allows_multiple_pdfs_and_has_batch_result_panel(self):
        root = os.getcwd()
        with open(os.path.join(root, "templates", "index.html"), encoding="utf-8") as handle:
            template = handle.read()

        self.assertIn('id="fileInput" accept=".pdf" multiple', template)
        self.assertIn('id="batchResult"', template)
        self.assertIn('id="batchIdText"', template)
        self.assertIn('id="batchAcceptedList"', template)
        self.assertIn('id="batchErrorList"', template)
        self.assertIn("Processing has not started yet.", template)

    def test_upload_script_creates_batch_for_multiple_pdfs_without_starting_it(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("let selectedFiles = []", script)
        self.assertIn("selectFiles(fileInput.files)", script)
        self.assertIn("selectedFiles.forEach(file => formData.append('files', file))", script)
        self.assertIn("fetch('/api/batches', { method: 'POST', body: formData })", script)
        self.assertIn("renderBatchResult(data)", script)
        self.assertIn("Batch created. Processing has not started yet.", script)
        self.assertNotIn("/api/batches/${", script)
        self.assertNotIn("/start", script)

    def test_upload_script_preserves_single_pdf_colorization_flow(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("if (selectedFiles.length > 1)", script)
        self.assertIn("formData.append('file', selectedFile)", script)
        self.assertIn("fetch('/upload', { method: 'POST', body: formData })", script)
        self.assertIn("fetch(`/api/colorize/${data.job_id}`, { method: 'POST' })", script)
        self.assertIn("window.location.href = `/processing/${data.job_id}`", script)

    def test_upload_script_blocks_reference_batch_for_now(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("selectedFiles.length > 1 && mode === 'reference'", script)
        self.assertIn("Batch creation supports Auto mode only", script)
        self.assertIn("formData.append('mode', 'auto')", script)


if __name__ == "__main__":
    unittest.main()
