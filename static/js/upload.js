/* ColorComic — Upload page logic */

const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const fileInfo = document.getElementById('fileInfo');

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

function selectFiles(fileList) {
    selectedFiles = Array.from(fileList).filter(isPdfFile);
    selectedFile = selectedFiles.length ? selectedFiles[0] : null;

    if (!selectedFiles.length) {
        fileInfo.style.display = 'none';
        hideBatchResult();
        updateUploadButtonState();
        return;
    }

    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const fileHint = document.getElementById('fileHint');
    const totalSize = selectedFiles.reduce((sum, file) => sum + file.size, 0);
    const sizeMB = (totalSize / (1024 * 1024)).toFixed(1);

    if (selectedFiles.length === 1) {
        fileName.textContent = selectedFile.name;
        fileSize.textContent = `(${sizeMB} MB)`;
        fileHint.textContent = 'Single PDF selected. Upload will start the normal colorization flow.';
    } else {
        fileName.textContent = `${selectedFiles.length} PDFs selected`;
        fileSize.textContent = `(${sizeMB} MB total)`;
        fileHint.textContent = 'Batch creation supports Auto mode only and will not start processing yet.';
    }
    fileInfo.style.display = 'block';
    hideBatchResult();
    updateUploadButtonState();
}

// ── Colorization Mode Toggle ────────────────────────────────────────────────

const modeRadios = document.querySelectorAll('input[name="mode"]');
const referenceSection = document.getElementById('referenceSection');
const prefOpenOutputFolder = document.getElementById('prefOpenOutputFolder');
const savePreferencesBtn = document.getElementById('savePreferencesBtn');
const preferencesStatus = document.getElementById('preferencesStatus');

function updateModeSection() {
    const isReference = getSelectedMode() === 'reference';
    referenceSection.style.display = isReference ? 'block' : 'none';
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

if (savePreferencesBtn) {
    savePreferencesBtn.addEventListener('click', savePreferences);
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
const batchAcceptedList = document.getElementById('batchAcceptedList');
const batchErrorsBlock = document.getElementById('batchErrorsBlock');
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

function appendBatchListItem(list, primary, secondary) {
    const item = document.createElement('li');
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
    return status.charAt(0).toUpperCase() + status.slice(1);
}

function renderBatchCounts(counts) {
    if (!batchCounts || !counts) return;

    batchCounts.replaceChildren();
    ['queued', 'running', 'completed', 'failed', 'cancelled'].forEach(status => {
        const item = document.createElement('span');
        item.className = `status batch-status-${status}`;
        item.textContent = `${formatStatus(status)}: ${counts[status] || 0}`;
        batchCounts.appendChild(item);
    });
    batchCounts.style.display = 'flex';
}

function renderBatchJobs(jobs) {
    batchAcceptedList.replaceChildren();
    jobs.forEach(job => {
        const details = [];
        details.push(formatStatus(job.status));
        if (Number.isInteger(job.page_count)) {
            details.push(`${job.page_count} page${job.page_count === 1 ? '' : 's'}`);
        }
        if (job.error) details.push(job.error);
        appendBatchListItem(batchAcceptedList, job.original_filename || job.filename || job.job_id, details.join(' - '));
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

function renderBatchStatus(data) {
    if (!data) return;

    currentBatchId = data.batch_id || currentBatchId;
    batchIdText.textContent = currentBatchId ? `Batch ID: ${currentBatchId}` : 'No batch was created.';
    batchStatusText.textContent = `Batch status: ${formatStatus(data.status)}`;
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
        appendBatchListItem(batchAcceptedList, job.filename || job.job_id, pageText);
    });
    errors.forEach(error => {
        appendBatchListItem(
            batchErrorList,
            error.filename || 'File',
            error.message || error.code || 'Could not prepare this PDF.',
        );
    });

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
    details.appendChild(actionStatus);

    item.appendChild(details);

    const actions = document.createElement('div');
    actions.className = 'recent-output-actions';

    if (job.output_pdf_exists && job.output_pdf_safe) {
        const download = document.createElement('a');
        download.className = 'btn btn-primary btn-sm';
        download.href = `/api/download/${encodeURIComponent(job.job_id)}`;
        download.textContent = 'Download';
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
    } else {
        const unavailable = document.createElement('span');
        unavailable.className = 'status status-error';
        unavailable.textContent = 'Unavailable';
        actions.appendChild(unavailable);
    }

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
loadPreferences();
loadRecentOutputs();
