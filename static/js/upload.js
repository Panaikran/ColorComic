/* ColorComic — Upload page logic */

const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const fileInfo = document.getElementById('fileInfo');

let selectedFile = null;
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
    if (files.length && files[0].name.toLowerCase().endsWith('.pdf')) {
        selectFile(files[0]);
    }
});

fileInput.addEventListener('change', () => {
    if (fileInput.files.length) selectFile(fileInput.files[0]);
});

function selectFile(file) {
    selectedFile = file;
    document.getElementById('fileName').textContent = file.name;
    const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
    document.getElementById('fileSize').textContent = `(${sizeMB} MB)`;
    fileInfo.style.display = 'block';
    updateUploadButtonState();
}

// ── Colorization Mode Toggle ────────────────────────────────────────────────

const modeRadios = document.querySelectorAll('input[name="mode"]');
const referenceSection = document.getElementById('referenceSection');

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
}

function applyDevicePreference(defaultDevice) {
    if (defaultDevice !== 'cpu') return;

    const cpuDevice = document.querySelector('input[name="device"][value="cpu"]');
    if (cpuDevice) cpuDevice.checked = true;
}

async function loadPreferences() {
    try {
        const response = await fetch('/api/preferences');
        if (!response.ok) return;
        const data = await response.json();
        const preferences = data && data.preferences ? data.preferences : {};

        applyModePreference(preferences.default_mode);
        applyDevicePreference(preferences.default_device);
    } catch (error) {
        // Keep the built-in form defaults when preferences are unavailable.
    }
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
    if (!selectedFile) {
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

uploadBtn.addEventListener('click', async () => {
    if (!selectedFile) return;
    uploadBtn.disabled = true;

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
