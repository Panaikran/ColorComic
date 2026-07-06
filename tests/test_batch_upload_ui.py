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
        self.assertIn('id="startBatchBtn"', template)
        self.assertIn('id="batchStatusText"', template)
        self.assertIn('id="batchCounts"', template)
        self.assertIn('id="selectedFilesList"', template)
        self.assertIn('id="batchAcceptedList"', template)
        self.assertIn('id="batchErrorList"', template)
        self.assertIn("Processing has not started yet.", template)

    def test_upload_script_creates_batch_for_multiple_pdfs_and_waits_for_user_start(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("let selectedFiles = []", script)
        self.assertIn("selectFiles(fileInput.files)", script)
        self.assertIn("selectedFiles.forEach(file => formData.append('files', file))", script)
        self.assertIn("fetch('/api/batches', { method: 'POST', body: formData })", script)
        self.assertIn("renderBatchResult(data)", script)
        self.assertIn("Batch created. Processing has not started yet.", script)
        self.assertIn("startBatchBtn.style.display = data.batch_id ? '' : 'none'", script)
        self.assertIn("startBatchBtn.addEventListener('click', startCurrentBatch)", script)

    def test_upload_script_shows_selected_file_list_for_batches_only(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("const selectedFilesList = document.getElementById('selectedFilesList')", script)
        self.assertIn("function renderSelectedFilesList()", script)
        self.assertIn("selectedFilesList.replaceChildren()", script)
        self.assertIn("if (selectedFiles.length <= 1)", script)
        self.assertIn("selectedFilesList.style.display = 'none'", script)
        self.assertIn("selectedFiles.forEach(file =>", script)
        self.assertIn("item.textContent = `${file.name} (${formatFileSize(file.size)} MB)`", script)
        self.assertIn("selectedFilesList.style.display = 'block'", script)

    def test_upload_script_starts_batch_and_polls_status(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("async function startCurrentBatch()", script)
        self.assertIn("fetch(`/api/batches/${encodeURIComponent(currentBatchId)}/start`, { method: 'POST' })", script)
        self.assertIn("startBatchPolling(currentBatchId)", script)
        self.assertIn("fetch(`/api/batches/${encodeURIComponent(batchId)}`)", script)
        self.assertIn("setInterval(() =>", script)
        self.assertIn("terminalBatchStatuses.has(data.status)", script)
        self.assertIn("clearInterval(batchPollTimer)", script)

    def test_upload_script_renders_batch_counts_statuses_and_errors(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("function renderBatchStatus(data)", script)
        self.assertIn("function renderBatchCounts(counts)", script)
        self.assertIn("function renderBatchJobs(jobs)", script)
        self.assertIn("'queued', 'running', 'completed', 'failed', 'cancelled'", script)
        self.assertIn("if (job.error) details.push(job.error)", script)

    def test_upload_script_shows_completed_batch_output_actions_only_when_safe(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        batch_section = script.split("function renderBatchJobs(jobs)", 1)[1].split("function stopBatchPolling()", 1)[0]
        self.assertIn("job.status === 'completed' && job.output_pdf_exists && job.output_pdf_safe", batch_section)
        self.assertIn("download.href = job.download_url || `/api/download/${encodeURIComponent(job.job_id)}`", batch_section)
        self.assertIn("download.textContent = 'Download PDF'", batch_section)
        self.assertIn("if (canOpenOutputPdf())", batch_section)
        self.assertIn("if (canOpenOutputFolder())", batch_section)
        self.assertIn("openRecentOutputPdf(job.job_id, actionStatus, revealPdf)", batch_section)
        self.assertIn("openRecentOutputFolder(job.job_id, actionStatus, openFolder)", batch_section)

    def test_upload_script_shows_cancel_for_queued_batch_jobs_only(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        batch_section = script.split("function renderBatchJobs(jobs)", 1)[1].split("function stopBatchPolling()", 1)[0]
        self.assertIn("if (job.status === 'queued')", batch_section)
        self.assertIn("cancel.textContent = 'Cancel'", batch_section)
        self.assertIn("cancelQueuedBatchJob(job.job_id, actionStatus, cancel)", batch_section)
        self.assertNotIn("job.status === 'running'", batch_section)
        self.assertNotIn("job.status === 'failed'", batch_section)
        self.assertNotIn("job.status === 'cancelled'", batch_section)

    def test_upload_script_cancels_queued_job_and_refreshes_batch_status(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("async function cancelQueuedBatchJob(jobId, statusElement, button)", script)
        self.assertIn("`/api/batches/${encodeURIComponent(currentBatchId)}/jobs/${encodeURIComponent(jobId)}/cancel`", script)
        self.assertIn("{ method: 'POST' }", script)
        self.assertIn("await pollBatchStatus(currentBatchId)", script)
        self.assertIn("Could not cancel this job.", script)

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
