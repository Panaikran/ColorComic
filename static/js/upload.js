/* ColorComic — Upload page logic */

const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const fileInfo = document.getElementById('fileInfo');
const batchModeNotice = document.getElementById('batchModeNotice');
const selectedFilesList = document.getElementById('selectedFilesList');

let selectedFile = null;
let selectedFiles = [];
let selectedRefFile = null;

// ── PDF Drag and Drop ───────────────────────────────────────────────────────

dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', e => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length) selectFiles(files);
});

fileInput.addEventListener('change', () => {
    if (fileInput.files.length) selectFiles(fileInput.files);
});

function isPdfFile(file) {
    return /\.pdf$/i.test(file.name);
}

function formatFileSize(bytes) {
    return (bytes / (1024 * 1024)).toFixed(1);
}

function renderSelectedFilesList() {
    if (!selectedFilesList) return;

    selectedFilesList.replaceChildren();
    if (selectedFiles.length <= 1) {
        selectedFilesList.style.display = 'none';
        return;
    }

    selectedFiles.forEach((file, index) => {
        const item = document.createElement('li');
        item.style.marginBottom = '0.35rem';

        const label = document.createElement('span');
        label.textContent = `${file.name} (${formatFileSize(file.size)} MB)`;
        item.appendChild(label);

        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'btn btn-sm btn-secondary';
        remove.textContent = 'Remove';
        remove.setAttribute('aria-label', `Remove ${file.name}`);
        remove.style.marginLeft = '0.5rem';
        remove.addEventListener('click', () => removeSelectedFile(index));
        item.appendChild(remove);

        selectedFilesList.appendChild(item);
    });
    selectedFilesList.style.display = 'block';
}

function removeSelectedFile(index) {
    selectedFiles.splice(index, 1);
    if (!selectedFiles.length) fileInput.value = '';
    selectFiles(selectedFiles);
}

function updateBatchModeNotice() {
    if (!batchModeNotice) return;

    if (selectedFiles.length <= 1) {
        batchModeNotice.style.display = 'none';
        batchModeNotice.textContent = '';
        return;
    }

    const suffix = getSelectedMode() === 'reference'
        ? ' Select Auto mode to create this batch.'
        : '';
    batchModeNotice.textContent = `Batch processing currently supports Auto mode only. Reference mode is available only for single-PDF processing.${suffix}`;
    batchModeNotice.style.display = 'block';
}

function selectFiles(fileList) {
    selectedFiles = Array.from(fileList).filter(isPdfFile);
    selectedFile = selectedFiles.length ? selectedFiles[0] : null;

    if (!selectedFiles.length) {
        fileInfo.style.display = 'none';
        updateBatchModeNotice();
        renderSelectedFilesList();
        hideBatchResult();
        updateUploadButtonState();
        return;
    }

    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const fileHint = document.getElementById('fileHint');
    const totalSize = selectedFiles.reduce((sum, file) => sum + file.size, 0);
    const sizeMB = formatFileSize(totalSize);

    if (selectedFiles.length === 1) {
        fileName.textContent = selectedFile.name;
        fileSize.textContent = `(${sizeMB} MB)`;
        fileHint.textContent = 'Single PDF selected. Upload will start the normal colorization flow.';
    } else {
        fileName.textContent = `${selectedFiles.length} PDFs selected`;
        fileSize.textContent = `(${sizeMB} MB total)`;
        fileHint.textContent = 'Review the selected PDFs, then create the batch.';
    }
    updateBatchModeNotice();
    renderSelectedFilesList();
    fileInfo.style.display = 'block';
    hideBatchResult();
    updateUploadButtonState();
}

// ── Colorization Mode Toggle ────────────────────────────────────────────────

const modeRadios = document.querySelectorAll('input[name="mode"]');
const referenceSection = document.getElementById('referenceSection');
const prefOpenOutputFolder = document.getElementById('prefOpenOutputFolder');
const savePreferencesBtn = document.getElementById('savePreferencesBtn');
const resetPreferencesBtn = document.getElementById('resetPreferencesBtn');
const openLogsFolderBtn = document.getElementById('openLogsFolderBtn');
const preferencesStatus = document.getElementById('preferencesStatus');

function updateModeSection() {
    const isReference = getSelectedMode() === 'reference';
    referenceSection.style.display = isReference ? 'block' : 'none';
    updateBatchModeNotice();
    updateUploadButtonState();
}

modeRadios.forEach(radio => {
    radio.addEventListener('change', updateModeSection);
});

function getSelectedMode() {
    const checked = document.querySelector('input[name="mode"]:checked');
    return checked ? checked.value : 'auto';
}

function applyModePreference(defaultMode) {
    if (defaultMode !== 'auto' && defaultMode !== 'reference') return;

    const preferredMode = document.querySelector(`input[name="mode"][value="${defaultMode}"]`);
    if (!preferredMode) return;

    preferredMode.checked = true;
    updateModeSection();

    const preferredSetting = document.querySelector(`input[name="prefDefaultMode"][value="${defaultMode}"]`);
    if (preferredSetting) preferredSetting.checked = true;
}

function applyDevicePreference(defaultDevice) {
    if (defaultDevice !== 'cpu') return;

    const cpuDevice = document.querySelector('input[name="device"][value="cpu"]');
    if (cpuDevice) cpuDevice.checked = true;
}

function applyOutputFolderPreference(openOutputFolder) {
    if (typeof openOutputFolder !== 'boolean' || !prefOpenOutputFolder) return;
    prefOpenOutputFolder.checked = openOutputFolder;
}

function setPreferencesStatus(message, kind) {
    if (!preferencesStatus) return;

    preferencesStatus.textContent = message;
    preferencesStatus.classList.remove('is-success', 'is-error');
    if (kind) preferencesStatus.classList.add(`is-${kind}`);
}

function canOpenLogsFolder() {
    return Boolean(
        window.pywebview
        && window.pywebview.api
        && window.pywebview.api.open_logs_folder
    );
}

function updateLogsFolderAction() {
    if (!openLogsFolderBtn) return;
    openLogsFolderBtn.style.display = canOpenLogsFolder() ? '' : 'none';
}

function getSelectedPreferenceMode() {
    const checked = document.querySelector('input[name="prefDefaultMode"]:checked');
    return checked ? checked.value : 'auto';
}

function applyPreferences(preferences) {
    applyModePreference(preferences.default_mode);
    applyDevicePreference(preferences.default_device);
    applyOutputFolderPreference(preferences.open_output_folder_after_completion);
}

async function loadPreferences() {
    try {
        const response = await fetch('/api/preferences');
        if (!response.ok) return;
        const data = await response.json();
        const preferences = data && data.preferences ? data.preferences : {};

        applyPreferences(preferences);
    } catch (error) {
        // Keep the built-in form defaults when preferences are unavailable.
    }
}

async function savePreferences() {
    if (!savePreferencesBtn) return;

    setPreferencesStatus('Saving...', '');
    savePreferencesBtn.disabled = true;
    try {
        const response = await fetch('/api/preferences', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                default_mode: getSelectedPreferenceMode(),
                default_device: 'cpu',
                open_output_folder_after_completion: Boolean(prefOpenOutputFolder && prefOpenOutputFolder.checked),
            }),
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data && data.error ? data.error : 'Could not save preferences.');
        }

        const preferences = data && data.preferences ? data.preferences : {};
        applyPreferences(preferences);
        setPreferencesStatus('Preferences saved.', 'success');
    } catch (error) {
        setPreferencesStatus(
            error && error.message ? error.message : 'Could not save preferences.',
            'error',
        );
    } finally {
        savePreferencesBtn.disabled = false;
    }
}

async function resetPreferences() {
    if (!resetPreferencesBtn) return;

    setPreferencesStatus('Resetting...', '');
    resetPreferencesBtn.disabled = true;
    try {
        const response = await fetch('/api/preferences/reset', { method: 'POST' });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data && data.error ? data.error : 'Could not reset preferences.');
        }

        const preferences = data && data.preferences ? data.preferences : {};
        applyPreferences(preferences);
        setPreferencesStatus('Preferences reset to defaults.', 'success');
    } catch (error) {
        setPreferencesStatus(
            error && error.message ? error.message : 'Could not reset preferences.',
            'error',
        );
    } finally {
        resetPreferencesBtn.disabled = false;
    }
}

async function openLogsFolder() {
    if (!openLogsFolderBtn || !canOpenLogsFolder()) return;

    setPreferencesStatus('', '');
    openLogsFolderBtn.disabled = true;
    try {
        const result = await window.pywebview.api.open_logs_folder();
        if (!result || !result.ok) {
            throw new Error(result && result.error ? result.error : 'Could not open logs folder.');
        }
    } catch (error) {
        setPreferencesStatus(
            error && error.message ? error.message : 'Could not open logs folder.',
            'error',
        );
    } finally {
        openLogsFolderBtn.disabled = false;
    }
}

if (savePreferencesBtn) {
    savePreferencesBtn.addEventListener('click', savePreferences);
}

if (resetPreferencesBtn) {
    resetPreferencesBtn.addEventListener('click', resetPreferences);
}

if (openLogsFolderBtn) {
    openLogsFolderBtn.addEventListener('click', openLogsFolder);
}

// ── Reference Image Upload ──────────────────────────────────────────────────

const refDropZone = document.getElementById('refDropZone');
const refFileInput = document.getElementById('refFileInput');
const refPlaceholder = document.getElementById('refPlaceholder');
const refPreview = document.getElementById('refPreview');
const refPreviewImg = document.getElementById('refPreviewImg');
const refRemoveBtn = document.getElementById('refRemoveBtn');

refDropZone.addEventListener('click', (e) => {
    if (e.target === refRemoveBtn || e.target.closest('#refRemoveBtn')) return;
    refFileInput.click();
});

refDropZone.addEventListener('dragover', e => {
    e.preventDefault();
    refDropZone.classList.add('dragover');
});

refDropZone.addEventListener('dragleave', () => {
    refDropZone.classList.remove('dragover');
});

refDropZone.addEventListener('drop', e => {
    e.preventDefault();
    refDropZone.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length && isImageFile(files[0])) {
        selectRefFile(files[0]);
    }
});

refFileInput.addEventListener('change', () => {
    if (refFileInput.files.length) selectRefFile(refFileInput.files[0]);
});

refRemoveBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    clearRefFile();
});

function isImageFile(file) {
    return /\.(png|jpe?g|webp)$/i.test(file.name);
}

function selectRefFile(file) {
    selectedRefFile = file;
    const url = URL.createObjectURL(file);
    refPreviewImg.src = url;
    refPlaceholder.style.display = 'none';
    refPreview.style.display = 'block';
    updateUploadButtonState();
}

function clearRefFile() {
    selectedRefFile = null;
    refFileInput.value = '';
    refPlaceholder.style.display = 'block';
    refPreview.style.display = 'none';
    if (refPreviewImg.src) {
        URL.revokeObjectURL(refPreviewImg.src);
        refPreviewImg.src = '';
    }
    updateUploadButtonState();
}

// ── Upload Button State ─────────────────────────────────────────────────────

function updateUploadButtonState() {
    const mode = getSelectedMode();
    uploadBtn.textContent = selectedFiles.length > 1 ? 'Create Batch' : 'Upload & Colorize';
    if (!selectedFiles.length) {
        uploadBtn.disabled = true;
        return;
    }
    if (selectedFiles.length > 1 && mode === 'reference') {
        uploadBtn.disabled = true;
        return;
    }
    if (mode === 'reference' && !selectedRefFile) {
        uploadBtn.disabled = true;
        return;
    }
    uploadBtn.disabled = false;
}

// ── GPU Detection ───────────────────────────────────────────────────────────

document.getElementById('detectGpuBtn').addEventListener('click', async () => {
    const btn = document.getElementById('detectGpuBtn');
    const status = document.getElementById('gpuDetectStatus');
    const infoBox = document.getElementById('gpuInfoBox');
    const gpuLabel = document.getElementById('gpuRadioLabel');

    btn.disabled = true;
    status.textContent = 'Detecting...';

    try {
        const res = await fetch('/api/gpu-info');
        const data = await res.json();

        if (!data.available) {
            infoBox.style.display = 'block';
            infoBox.innerHTML = '<strong>No GPU detected.</strong><br><span class="text-dim">CUDA is not available. Using CPU mode.</span>';
            status.textContent = '';
            btn.disabled = false;
            return;
        }

        const gpu = data.gpus[0];
        const recText = data.recommended === 'cuda'
            ? '<span style="color:#4caf50;">Recommended: GPU</span>'
            : '<span style="color:#ff9800;">Recommended: CPU</span> (low VRAM)';

        infoBox.style.display = 'block';
        infoBox.innerHTML = `
            <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:0.5rem;">
                <div>
                    <strong>${gpu.name}</strong><br>
                    <span class="text-dim">VRAM:</span> ${gpu.vram_total_gb} GB total, ${gpu.vram_free_gb} GB free<br>
                    <span class="text-dim">Compute:</span> ${gpu.compute_capability} &middot; ${gpu.multi_processors} SMs<br>
                    <span class="text-dim">CUDA:</span> ${data.driver}
                </div>
                <div style="align-self:center;">${recText}</div>
            </div>
        `;

        // Show GPU radio and auto-select recommended
        gpuLabel.style.display = '';
        if (data.recommended === 'cuda') {
            document.querySelector('input[name="device"][value="cuda"]').checked = true;
        }

        status.textContent = '';
    } catch (err) {
        status.textContent = 'Detection failed';
        infoBox.style.display = 'block';
        infoBox.innerHTML = '<span class="text-dim">Could not detect GPU. Using CPU mode.</span>';
    }
    btn.disabled = false;
});

// ── Upload ──────────────────────────────────────────────────────────────────

const batchResult = document.getElementById('batchResult');
const batchIdText = document.getElementById('batchIdText');
const batchAcceptedBlock = document.getElementById('batchAcceptedBlock');
const batchAcceptedTitle = document.getElementById('batchAcceptedTitle');
const batchAcceptedList = document.getElementById('batchAcceptedList');
const batchErrorsBlock = document.getElementById('batchErrorsBlock');
const batchErrorsTitle = document.getElementById('batchErrorsTitle');
const batchErrorList = document.getElementById('batchErrorList');
const startBatchBtn = document.getElementById('startBatchBtn');
const batchStatusText = document.getElementById('batchStatusText');
const batchCounts = document.getElementById('batchCounts');
const terminalBatchStatuses = new Set(['completed', 'failed', 'cancelled']);
let currentBatchId = null;
let batchPollTimer = null;

function hideBatchResult() {
    if (batchResult) batchResult.style.display = 'none';
    stopBatchPolling();
    currentBatchId = null;
}

function appendBatchListItem(list, primary, secondary, statusLabel) {
    const item = document.createElement('li');
    if (statusLabel) {
        const label = document.createElement('span');
        label.className = 'text-dim';
        label.textContent = `${statusLabel}: `;
        item.appendChild(label);
    }
    const strong = document.createElement('strong');
    strong.textContent = primary;
    item.appendChild(strong);
    if (secondary) {
        const meta = document.createElement('span');
        meta.className = 'text-dim';
        meta.textContent = ` - ${secondary}`;
        item.appendChild(meta);
    }
    list.appendChild(item);
}

function formatStatus(status) {
    if (!status) return 'Unknown';
    if (status === 'recovery_required') return 'Recovery required';
    return status.charAt(0).toUpperCase() + status.slice(1);
}

function formatRetryAttempt(job) {
    if (!Number.isInteger(job.attempt_number) || job.attempt_number <= 1) return '';
    return `Retry ${job.attempt_number - 1}`;
}

function renderBatchCounts(counts) {
    if (!batchCounts || !counts) return;

    batchCounts.replaceChildren();
    ['queued', 'paused', 'running', 'failed', 'recovery_required', 'completed', 'cancelled'].forEach(status => {
        const item = document.createElement('span');
        item.className = `status batch-status-${status}`;
        item.textContent = `${formatStatus(status)}: ${counts[status] || 0}`;
        batchCounts.appendChild(item);
    });
    batchCounts.style.display = 'flex';
}

const queueActionLabels = {
    pause: 'Pause',
    resume: 'Resume',
    retry: 'Retry',
    remove: 'Remove',
    move_up: 'Move Up',
    move_down: 'Move Down',
};

const queueActionPaths = {
    pause: 'pause',
    resume: 'resume',
    retry: 'retry',
    remove: 'remove',
    move_up: 'move-up',
    move_down: 'move-down',
};

async function applyQueueJobAction(job, action, statusElement, button) {
    if (!currentBatchId) return;

    const actionPath = queueActionPaths[action];
    const label = queueActionLabels[action] || 'Update';
    if (!actionPath) return;
    statusElement.textContent = '';
    button.disabled = true;
    try {
        const response = await fetch(
            `/api/batches/${encodeURIComponent(currentBatchId)}/jobs/${encodeURIComponent(job.job_id)}/${actionPath}`,
            { method: 'POST' },
        );
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data && data.error ? data.error : 'Could not update this job.');
        }
        statusElement.textContent = `${label} complete.`;
        await pollBatchStatus(currentBatchId);
    } catch (error) {
        statusElement.textContent = error && error.message ? error.message : 'Could not update this job.';
        button.disabled = false;
    }
}

function renderBatchJobs(jobs) {
    batchAcceptedList.replaceChildren();
    jobs.forEach(job => {
        const item = document.createElement('li');
        item.className = `batch-job batch-job-${job.status || 'unknown'}`;
        if (job.status === 'recovery_required') item.classList.add('batch-job-recovery_required');
        const title = document.createElement('strong');
        title.textContent = job.original_filename || job.filename || job.job_id;
        item.appendChild(title);

        const details = [];
        details.push(formatStatus(job.status));
        if (Number.isInteger(job.page_count)) {
            details.push(`${job.page_count} page${job.page_count === 1 ? '' : 's'}`);
        }
        const retryAttempt = formatRetryAttempt(job);
        if (retryAttempt) details.push(retryAttempt);
        if (job.error) details.push(job.error);
        const meta = document.createElement('span');
        meta.className = 'text-dim';
        meta.textContent = ` - ${details.join(' - ')}`;
        item.appendChild(meta);

        if (Array.isArray(job.actions) && job.actions.length) {
            const actionStatus = document.createElement('p');
            actionStatus.className = 'text-dim recent-output-action-status';
            actionStatus.setAttribute('role', 'status');
            actionStatus.setAttribute('aria-live', 'polite');

            const actions = document.createElement('div');
            actions.className = 'recent-output-actions';

            job.actions.forEach(action => {
                const label = queueActionLabels[action];
                if (!label) return;
                const button = document.createElement('button');
                button.className = 'btn btn-secondary btn-sm';
                button.type = 'button';
                button.textContent = label;
                button.setAttribute('aria-label', `${label} ${job.original_filename || job.filename || job.job_id}`);
                button.addEventListener('click', () => applyQueueJobAction(job, action, actionStatus, button));
                actions.appendChild(button);
            });

            item.appendChild(actionStatus);
            item.appendChild(actions);
        }

        if (job.status === 'completed' && job.output_pdf_exists && job.output_pdf_safe) {
            const actionStatus = document.createElement('p');
            actionStatus.className = 'text-dim recent-output-action-status';
            actionStatus.setAttribute('role', 'status');
            actionStatus.setAttribute('aria-live', 'polite');

            const actions = document.createElement('div');
            actions.className = 'recent-output-actions';

            const download = document.createElement('a');
            download.className = 'btn btn-primary btn-sm';
            download.href = job.download_url || `/api/download/${encodeURIComponent(job.job_id)}`;
            download.textContent = 'Download PDF';
            actions.appendChild(download);

            if (canOpenOutputPdf()) {
                const revealPdf = document.createElement('button');
                revealPdf.className = 'btn btn-secondary btn-sm';
                revealPdf.type = 'button';
                revealPdf.textContent = 'Show PDF';
                revealPdf.addEventListener('click', () => {
                    openRecentOutputPdf(job.job_id, actionStatus, revealPdf);
                });
                actions.appendChild(revealPdf);
            }

            if (canOpenOutputFolder()) {
                const openFolder = document.createElement('button');
                openFolder.className = 'btn btn-secondary btn-sm';
                openFolder.type = 'button';
                openFolder.textContent = 'Open Folder';
                openFolder.addEventListener('click', () => {
                    openRecentOutputFolder(job.job_id, actionStatus, openFolder);
                });
                actions.appendChild(openFolder);
            }

            item.appendChild(actionStatus);
            item.appendChild(actions);
        }

        batchAcceptedList.appendChild(item);
    });
    batchAcceptedBlock.style.display = jobs.length ? 'block' : 'none';
}

function stopBatchPolling() {
    if (!batchPollTimer) return;
    clearInterval(batchPollTimer);
    batchPollTimer = null;
}

async function pollBatchStatus(batchId) {
    const response = await fetch(`/api/batches/${encodeURIComponent(batchId)}`);
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data && data.error ? data.error : 'Could not load batch status.');
    }

    renderBatchStatus(data);
    if (terminalBatchStatuses.has(data.status)) {
        stopBatchPolling();
    }
}

function startBatchPolling(batchId) {
    stopBatchPolling();
    pollBatchStatus(batchId).catch(error => {
        batchStatusText.textContent = error.message;
        stopBatchPolling();
    });
    batchPollTimer = setInterval(() => {
        pollBatchStatus(batchId).catch(error => {
            batchStatusText.textContent = error.message;
            stopBatchPolling();
        });
    }, 2000);
}

function getBatchSummary(data) {
    const counts = data.counts || {};
    if (counts.paused > 0 && counts.queued === 0 && counts.running === 0) {
        return 'Queue paused. Worker is idle because all remaining jobs are paused.';
    }
    if (counts.recovery_required > 0) {
        return 'Recovery required after restart. Retry or remove affected jobs.';
    }
    if (counts.failed > 0) {
        return 'Retryable failures remain. Retry failed jobs to continue.';
    }
    if (data.status === 'completed') {
        return 'Queue completed successfully.';
    }
    if (counts.running > 0) {
        return 'Worker is processing queued work.';
    }
    if (counts.queued > 0) {
        return `Queue ready: ${counts.queued} queued.`;
    }
    return `Batch status: ${formatStatus(data.status)}`;
}

function renderBatchStatus(data) {
    if (!data) return;

    currentBatchId = data.batch_id || currentBatchId;
    batchIdText.textContent = currentBatchId ? `Batch ID: ${currentBatchId}` : 'No batch was created.';
    batchStatusText.textContent = getBatchSummary(data);
    renderBatchCounts(data.counts);
    renderBatchJobs(Array.isArray(data.jobs) ? data.jobs : []);
    if (startBatchBtn) {
        startBatchBtn.style.display = terminalBatchStatuses.has(data.status) || data.status === 'running'
            ? 'none'
            : '';
        startBatchBtn.disabled = data.status !== 'queued';
    }
}

function renderBatchResult(data) {
    if (!batchResult) return;

    const jobs = Array.isArray(data.jobs) ? data.jobs : [];
    const errors = Array.isArray(data.errors) ? data.errors : [];
    currentBatchId = data.batch_id || null;
    batchIdText.textContent = data.batch_id ? `Batch ID: ${data.batch_id}` : 'No batch was created.';
    batchStatusText.textContent = data.batch_id
        ? 'Processing has not started yet.'
        : 'No batch is ready to start.';
    batchAcceptedList.replaceChildren();
    batchErrorList.replaceChildren();
    if (batchCounts) batchCounts.style.display = 'none';
    if (startBatchBtn) {
        startBatchBtn.style.display = data.batch_id ? '' : 'none';
        startBatchBtn.disabled = !data.batch_id;
    }

    jobs.forEach(job => {
        const pageText = Number.isInteger(job.page_count)
            ? `${job.page_count} page${job.page_count === 1 ? '' : 's'}`
            : 'Queued';
        appendBatchListItem(batchAcceptedList, job.filename || job.job_id, pageText, 'Ready');
    });
    errors.forEach(error => {
        appendBatchListItem(
            batchErrorList,
            error.filename || 'File',
            error.message || error.code || 'Could not prepare this PDF.',
            'Rejected',
        );
    });

    if (batchAcceptedTitle) batchAcceptedTitle.textContent = `Accepted PDFs (${jobs.length})`;
    if (batchErrorsTitle) batchErrorsTitle.textContent = `Files That Need Attention (${errors.length})`;
    batchAcceptedBlock.style.display = jobs.length ? 'block' : 'none';
    batchErrorsBlock.style.display = errors.length ? 'block' : 'none';
    batchResult.style.display = 'block';
}

async function startCurrentBatch() {
    if (!currentBatchId || !startBatchBtn) return;

    startBatchBtn.disabled = true;
    batchStatusText.textContent = 'Starting batch...';
    try {
        const response = await fetch(`/api/batches/${encodeURIComponent(currentBatchId)}/start`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data && data.error ? data.error : 'Could not start batch.');
        }
        startBatchBtn.style.display = 'none';
        batchStatusText.textContent = 'Batch started. Checking progress...';
        startBatchPolling(currentBatchId);
    } catch (error) {
        batchStatusText.textContent = error && error.message ? error.message : 'Could not start batch.';
        startBatchBtn.disabled = false;
    }
}

if (startBatchBtn) {
    startBatchBtn.addEventListener('click', startCurrentBatch);
}

async function createBatchUpload() {
    const formData = new FormData();
    selectedFiles.forEach(file => formData.append('files', file));
    formData.append('mode', 'auto');

    const style = document.querySelector('input[name="style"]:checked');
    if (style) formData.append('style', style.value);

    const device = document.querySelector('input[name="device"]:checked');
    if (device) formData.append('device', device.value);

    const progress = document.getElementById('uploadProgress');
    progress.style.display = 'block';
    document.getElementById('uploadStatus').textContent = 'Creating batch...';
    document.getElementById('uploadFill').style.width = '40%';

    const res = await fetch('/api/batches', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok && data.error) throw new Error(data.error);

    renderBatchResult(data);
    document.getElementById('uploadFill').style.width = '100%';
    document.getElementById('uploadStatus').textContent = data.batch_id
        ? 'Batch created. Processing has not started yet.'
        : 'No PDFs were accepted for this batch.';
}

uploadBtn.addEventListener('click', async () => {
    if (!selectedFiles.length) return;
    uploadBtn.disabled = true;

    if (selectedFiles.length > 1) {
        try {
            await createBatchUpload();
        } catch (err) {
            document.getElementById('uploadProgress').style.display = 'block';
            document.getElementById('uploadStatus').textContent = 'Batch creation failed: ' + err.message;
        } finally {
            updateUploadButtonState();
        }
        return;
    }

    const formData = new FormData();
    formData.append('file', selectedFile);

    const mode = getSelectedMode();
    formData.append('mode', mode);

    if (mode === 'reference' && selectedRefFile) {
        formData.append('reference', selectedRefFile);
    }

    const style = document.querySelector('input[name="style"]:checked');
    if (style) formData.append('style', style.value);

    const device = document.querySelector('input[name="device"]:checked');
    if (device) formData.append('device', device.value);

    const progress = document.getElementById('uploadProgress');
    progress.style.display = 'block';
    document.getElementById('uploadStatus').textContent = 'Uploading PDF...';
    document.getElementById('uploadFill').style.width = '30%';

    try {
        const res = await fetch('/upload', { method: 'POST', body: formData });
        const data = await res.json();

        if (data.error) {
            document.getElementById('uploadStatus').textContent = 'Error: ' + data.error;
            uploadBtn.disabled = false;
            return;
        }

        document.getElementById('uploadFill').style.width = '60%';
        document.getElementById('uploadStatus').textContent = `Extracted ${data.page_count} pages. Starting colorization...`;

        // Start colorization
        await fetch(`/api/colorize/${data.job_id}`, { method: 'POST' });

        document.getElementById('uploadFill').style.width = '100%';

        // Redirect to processing page
        window.location.href = `/processing/${data.job_id}`;

    } catch (err) {
        document.getElementById('uploadStatus').textContent = 'Upload failed: ' + err.message;
        uploadBtn.disabled = false;
    }
});

// Recent outputs

const recentOutputsStatus = document.getElementById('recentOutputsStatus');
const recentOutputsList = document.getElementById('recentOutputsList');
const recentOutputsEmpty = document.getElementById('recentOutputsEmpty');
const recentOutputsError = document.getElementById('recentOutputsError');

function canOpenOutputFolder() {
    return Boolean(
        window.pywebview
        && window.pywebview.api
        && window.pywebview.api.open_output_folder
    );
}

function canOpenOutputPdf() {
    return Boolean(
        window.pywebview
        && window.pywebview.api
        && window.pywebview.api.open_output_pdf
    );
}

function formatMode(mode) {
    if (mode === 'reference') return 'Reference';
    return 'Auto';
}

function formatCompletedAt(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value || 'Unknown time';
    return date.toLocaleString([], {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
    });
}

function buildRecentOutputMeta(job) {
    const parts = [
        formatMode(job.mode),
        formatCompletedAt(job.completed_at),
    ];
    if (job.batch_id) {
        parts.splice(1, 0, `Batch ${job.batch_id}`);
    }
    if (Number.isInteger(job.page_count)) {
        parts.push(`${job.page_count} page${job.page_count === 1 ? '' : 's'}`);
    }
    if (!job.output_pdf_safe) {
        parts.push('Output path unavailable');
    } else if (!job.output_pdf_exists) {
        parts.push('Output file missing');
    }
    return parts.join(' - ');
}

async function openRecentOutputFolder(jobId, statusElement, button) {
    statusElement.textContent = '';
    button.disabled = true;
    try {
        const result = await window.pywebview.api.open_output_folder(jobId);
        if (!result || !result.ok) {
            statusElement.textContent = result && result.error
                ? result.error
                : 'Could not open the output folder.';
        }
    } catch (error) {
        statusElement.textContent = error && error.message
            ? error.message
            : 'Could not open the output folder.';
    } finally {
        button.disabled = false;
    }
}

async function openRecentOutputPdf(jobId, statusElement, button) {
    statusElement.textContent = '';
    button.disabled = true;
    try {
        const result = await window.pywebview.api.open_output_pdf(jobId);
        if (!result || !result.ok) {
            statusElement.textContent = result && result.error
                ? result.error
                : 'Could not show the PDF in Explorer.';
        }
    } catch (error) {
        statusElement.textContent = error && error.message
            ? error.message
            : 'Could not show the PDF in Explorer.';
    } finally {
        button.disabled = false;
    }
}

async function removeRecentOutput(jobId, item, statusElement, button) {
    statusElement.textContent = 'Removing from list only...';
    button.disabled = true;
    try {
        const response = await fetch(`/api/recent-jobs/${encodeURIComponent(jobId)}`, {
            method: 'DELETE',
        });
        const result = await response.json();
        if (!response.ok || !result || result.removed !== true) {
            throw new Error('Could not remove this output from the list.');
        }

        item.remove();
        const remaining = recentOutputsList.children.length;
        recentOutputsStatus.textContent = remaining ? `${remaining} saved` : '';
        recentOutputsEmpty.style.display = remaining ? 'none' : 'block';
        recentOutputsList.style.display = remaining ? 'grid' : 'none';
    } catch (error) {
        statusElement.textContent = error && error.message
            ? error.message
            : 'Could not remove this output from the list.';
        button.disabled = false;
    }
}

function renderRecentOutput(job) {
    const item = document.createElement('article');
    item.className = 'recent-output-item';

    const details = document.createElement('div');
    details.className = 'recent-output-details';

    const title = document.createElement('h3');
    title.textContent = job.original_filename || 'Untitled PDF';
    details.appendChild(title);

    const meta = document.createElement('p');
    meta.className = 'text-dim';
    meta.textContent = buildRecentOutputMeta(job);
    details.appendChild(meta);

    const actionStatus = document.createElement('p');
    actionStatus.className = 'text-dim recent-output-action-status';
    actionStatus.setAttribute('role', 'status');
    actionStatus.setAttribute('aria-live', 'polite');
    details.appendChild(actionStatus);

    item.appendChild(details);

    const actions = document.createElement('div');
    actions.className = 'recent-output-actions';

    if (job.output_pdf_exists && job.output_pdf_safe) {
        const download = document.createElement('a');
        download.className = 'btn btn-primary btn-sm';
        download.href = `/api/download/${encodeURIComponent(job.job_id)}`;
        download.textContent = 'Download';
        download.setAttribute('aria-label', `Download ${title.textContent}`);
        actions.appendChild(download);

        if (canOpenOutputPdf()) {
            const revealPdf = document.createElement('button');
            revealPdf.className = 'btn btn-secondary btn-sm';
            revealPdf.type = 'button';
            revealPdf.textContent = 'Show PDF';
            revealPdf.setAttribute('aria-label', `Show PDF for ${title.textContent}`);
            revealPdf.addEventListener('click', () => {
                openRecentOutputPdf(job.job_id, actionStatus, revealPdf);
            });
            actions.appendChild(revealPdf);
        }

        if (canOpenOutputFolder()) {
            const openFolder = document.createElement('button');
            openFolder.className = 'btn btn-secondary btn-sm';
            openFolder.type = 'button';
            openFolder.textContent = 'Open Folder';
            openFolder.setAttribute('aria-label', `Open output folder for ${title.textContent}`);
            openFolder.addEventListener('click', () => {
                openRecentOutputFolder(job.job_id, actionStatus, openFolder);
            });
            actions.appendChild(openFolder);
        }
    } else {
        const unavailable = document.createElement('span');
        unavailable.className = 'status status-error';
        unavailable.textContent = 'Unavailable';
        actions.appendChild(unavailable);
    }

    const remove = document.createElement('button');
    remove.className = 'btn btn-secondary btn-sm';
    remove.type = 'button';
    remove.textContent = 'Remove from list';
    remove.setAttribute('aria-label', `Remove ${title.textContent} from Recent Outputs`);
    remove.title = 'Removes this history entry only. Output files stay on disk.';
    remove.addEventListener('click', () => {
        removeRecentOutput(job.job_id, item, actionStatus, remove);
    });
    actions.appendChild(remove);

    item.appendChild(actions);
    return item;
}

async function loadRecentOutputs() {
    if (!recentOutputsList) return;

    recentOutputsStatus.textContent = 'Loading...';
    recentOutputsList.style.display = 'none';
    recentOutputsEmpty.style.display = 'none';
    recentOutputsError.style.display = 'none';

    try {
        const response = await fetch('/api/recent-jobs');
        if (!response.ok) throw new Error('Recent outputs request failed');
        const data = await response.json();
        const jobs = Array.isArray(data.jobs) ? data.jobs : [];

        recentOutputsList.replaceChildren();
        if (!jobs.length) {
            recentOutputsStatus.textContent = '';
            recentOutputsEmpty.style.display = 'block';
            return;
        }

        jobs.forEach(job => {
            recentOutputsList.appendChild(renderRecentOutput(job));
        });
        recentOutputsStatus.textContent = `${jobs.length} saved`;
        recentOutputsList.style.display = 'grid';
    } catch (error) {
        recentOutputsStatus.textContent = '';
        recentOutputsError.style.display = 'block';
    }
}

document.addEventListener('pywebviewready', loadRecentOutputs);
document.addEventListener('pywebviewready', updateLogsFolderAction);
updateLogsFolderAction();
loadPreferences();
loadRecentOutputs();
