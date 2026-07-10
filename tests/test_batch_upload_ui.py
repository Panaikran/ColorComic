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
        self.assertIn('id="uploadStatus" role="status" aria-live="polite"', template)
        self.assertIn('id="batchStatusText" role="status" aria-live="polite"', template)
        self.assertIn('id="batchCounts" role="status" aria-live="polite"', template)
        self.assertIn('id="batchModeNotice"', template)
        self.assertIn('id="selectedFilesList"', template)
        self.assertIn('id="batchAcceptedTitle"', template)
        self.assertIn('id="batchErrorsTitle"', template)
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

    def test_upload_script_labels_batch_creation_results_with_counts(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("const batchAcceptedTitle = document.getElementById('batchAcceptedTitle')", script)
        self.assertIn("const batchErrorsTitle = document.getElementById('batchErrorsTitle')", script)
        self.assertIn("function appendBatchListItem(list, primary, secondary, statusLabel)", script)
        self.assertIn("label.textContent = `${statusLabel}: `", script)
        self.assertIn("appendBatchListItem(batchAcceptedList, job.filename || job.job_id, pageText, 'Ready')", script)
        self.assertIn("'Rejected',", script)
        self.assertIn("batchAcceptedTitle.textContent = `Accepted PDFs (${jobs.length})`", script)
        self.assertIn("batchErrorsTitle.textContent = `Files That Need Attention (${errors.length})`", script)

    def test_upload_script_shows_auto_only_notice_for_batch_selection(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("const batchModeNotice = document.getElementById('batchModeNotice')", script)
        self.assertIn("function updateBatchModeNotice()", script)
        self.assertIn("if (selectedFiles.length <= 1)", script)
        self.assertIn("batchModeNotice.style.display = 'none'", script)
        self.assertIn("Batch processing currently supports Auto mode only.", script)
        self.assertIn("Reference mode is available only for single-PDF processing.", script)
        self.assertIn("Select Auto mode to create this batch.", script)
        self.assertIn("updateBatchModeNotice()", script)

    def test_upload_script_shows_selected_file_list_for_batches_only(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("const selectedFilesList = document.getElementById('selectedFilesList')", script)
        self.assertIn("function renderSelectedFilesList()", script)
        self.assertIn("selectedFilesList.replaceChildren()", script)
        self.assertIn("if (selectedFiles.length <= 1)", script)
        self.assertIn("selectedFilesList.style.display = 'none'", script)
        self.assertIn("selectedFiles.forEach((file, index) =>", script)
        self.assertIn("label.textContent = `${file.name} (${formatFileSize(file.size)} MB)`", script)
        self.assertIn("selectedFilesList.style.display = 'block'", script)

    def test_upload_script_removes_selected_files_before_batch_creation(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("remove.textContent = 'Remove'", script)
        self.assertIn("remove.setAttribute('aria-label', `Remove ${file.name}`)", script)
        self.assertIn("remove.addEventListener('click', () => removeSelectedFile(index))", script)
        self.assertIn("function removeSelectedFile(index)", script)
        self.assertIn("selectedFiles.splice(index, 1)", script)
        self.assertIn("if (!selectedFiles.length) fileInput.value = ''", script)
        self.assertIn("selectFiles(selectedFiles)", script)

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
        self.assertIn("'queued', 'paused', 'running', 'failed', 'recovery_required', 'completed', 'cancelled'", script)
        self.assertIn("if (job.error) details.push(job.error)", script)
        self.assertIn("item.className = `batch-job batch-job-${job.status || 'unknown'}`", script)

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

    def test_upload_script_renders_server_provided_queue_controls_with_accessible_names(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        batch_section = script.split("function renderBatchJobs(jobs)", 1)[1].split("function stopBatchPolling()", 1)[0]
        self.assertIn("const queueActionLabels = {", script)
        self.assertIn("pause: 'Pause'", script)
        self.assertIn("resume: 'Resume'", script)
        self.assertIn("retry: 'Retry'", script)
        self.assertIn("remove: 'Remove'", script)
        self.assertIn("move_up: 'Move Up'", script)
        self.assertIn("move_down: 'Move Down'", script)
        self.assertIn("Array.isArray(job.actions)", batch_section)
        self.assertIn("button.setAttribute('aria-label', `${label} ${job.original_filename || job.filename || job.job_id}`)", batch_section)
        self.assertIn("button.addEventListener('click', () => applyQueueJobAction(job, action, actionStatus, button))", batch_section)
        self.assertIn("actionStatus.setAttribute('role', 'status')", batch_section)
        self.assertIn("actionStatus.setAttribute('aria-live', 'polite')", batch_section)

    def test_upload_script_applies_queue_action_and_refreshes_batch_status(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("async function applyQueueJobAction(job, action, statusElement, button)", script)
        self.assertIn("const actionPath = queueActionPaths[action]", script)
        self.assertIn("`/api/batches/${encodeURIComponent(currentBatchId)}/jobs/${encodeURIComponent(job.job_id)}/${actionPath}`", script)
        self.assertIn("{ method: 'POST' }", script)
        self.assertIn("await pollBatchStatus(currentBatchId)", script)
        self.assertIn("Could not update this job.", script)
        self.assertIn("button.disabled = true", script)

    def test_upload_script_shows_retry_attempts_and_recovery_state(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "js", "upload.js"), encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("function formatRetryAttempt(job)", script)
        self.assertIn("return `Retry ${job.attempt_number - 1}`", script)
        self.assertIn("const retryAttempt = formatRetryAttempt(job)", script)
        self.assertIn("if (retryAttempt) details.push(retryAttempt)", script)
        self.assertIn("batch-job-recovery_required", script)

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
        self.assertIn("Batch processing currently supports Auto mode only", script)
        self.assertIn("formData.append('mode', 'auto')", script)


if __name__ == "__main__":
    unittest.main()
