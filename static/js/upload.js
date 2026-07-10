/* ColorComic — Upload page logic */

const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const submitHint = document.getElementById('submitHint');
const fileInfo = document.getElementById('fileInfo');
const dropError = document.getElementById('dropError');
const dropNote = document.getElementById('dropNote');

let selectedFile = null;

// ── PDF Drag and Drop ───────────────────────────────────────────────────────

function isPdfFile(file) {
    return file.name.toLowerCase().endsWith('.pdf');
}

function showDropError(msg) {
    dropError.textContent = msg;
    dropError.hidden = false;
    dropNote.hidden = true;
}

function showDropNote(msg) {
    dropNote.textContent = msg;
    dropNote.hidden = false;
}

function clearDropMessages() {
    dropError.hidden = true;
    dropNote.hidden = true;
}

dropZone.addEventListener('click', e => {
    if (e.target === fileInput) return;
    fileInput.click();
});

dropZone.addEventListener('keydown', e => {
    if (e.target !== dropZone) return;
    if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        fileInput.click();
    }
});

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
    const files = Array.from(e.dataTransfer.files);
    if (!files.length) return;
    const pdfs = files.filter(isPdfFile);
    if (!pdfs.length) {
        showDropError('Only PDF files are supported');
        return;
    }
    selectFile(pdfs[0]);
    if (files.length > 1) {
        showDropNote(`Using "${pdfs[0].name}" — ${files.length - 1} other file(s) ignored.`);
    }
});

fileInput.addEventListener('change', () => {
    if (fileInput.files.length) selectFile(fileInput.files[0]);
});

function selectFile(file) {
    clearDropMessages();
    selectedFile = file;
    document.getElementById('fileName').textContent = file.name;
    const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
    document.getElementById('fileSize').textContent = `(${sizeMB} MB)`;
    fileInfo.hidden = false;
    updateUploadButtonState();
    updateTimeEstimate();
}

// ── Mode toggle ─────────────────────────────────────────────────────────────

const modeRadios = document.querySelectorAll('input[name="mode"]');
const referenceSection = document.getElementById('referenceSection');
const llmModeNotice = document.getElementById('llmModeNotice');

modeRadios.forEach(radio => {
    radio.addEventListener('change', () => {
        const mode = getSelectedMode();
        referenceSection.hidden = mode !== 'reference';
        if (llmModeNotice) llmModeNotice.hidden = mode !== 'llm';
        const directorGroup = document.getElementById('directorGroup');
        if (directorGroup) directorGroup.hidden = mode !== 'auto';
        updateUploadButtonState();
    });
});

function getSelectedMode() {
    const checked = document.querySelector('input[name="mode"]:checked');
    return checked ? checked.value : 'auto';
}

// ── Reference (multi) ───────────────────────────────────────────────────────

const refDropZone = document.getElementById('refDropZone');
const refFileInput = document.getElementById('refFileInput');
const refList = document.getElementById('refList');
const refDropError = document.getElementById('refDropError');
const refDropNote = document.getElementById('refDropNote');

// Each entry: { file, url, rating: null|'checking'|'good'|'ok'|'poor'|'error', detail }
let refEntries = [];

function showRefError(msg) {
    refDropError.textContent = msg;
    refDropError.hidden = false;
    refDropNote.hidden = true;
}

function showRefNote(msg) {
    refDropNote.textContent = msg;
    refDropNote.hidden = false;
}

function clearRefMessages() {
    refDropError.hidden = true;
    refDropNote.hidden = true;
}

refDropZone.addEventListener('click', e => {
    if (e.target === refFileInput) return;
    refFileInput.click();
});

refDropZone.addEventListener('keydown', e => {
    if (e.target !== refDropZone) return;
    if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        refFileInput.click();
    }
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
    const files = Array.from(e.dataTransfer.files);
    if (!files.length) return;
    const images = files.filter(isImageFile);
    if (!images.length) {
        showRefError('Only PNG, JPG, or WEBP images are supported');
        return;
    }
    addRefFiles(images);
    if (images.length < files.length) {
        showRefNote(`${files.length - images.length} unsupported file(s) ignored.`);
    }
});

refFileInput.addEventListener('change', () => {
    addRefFiles(Array.from(refFileInput.files));
});

function isImageFile(file) {
    return /\.(png|jpe?g|webp)$/i.test(file.name);
}

function addRefFiles(files) {
    clearRefMessages();
    for (const f of files) {
        if (!isImageFile(f)) continue;
        const entry = { file: f, url: URL.createObjectURL(f), rating: 'checking', detail: '' };
        refEntries.push(entry);
        validateReferenceEntry(entry);
    }
    renderRefList();
    updateUploadButtonState();
}

function removeRefAt(idx) {
    const [removed] = refEntries.splice(idx, 1);
    if (removed) URL.revokeObjectURL(removed.url);
    renderRefList();
    updateUploadButtonState();
}

const REF_BADGE = {
    checking: { cls: '', label: 'Checking…' },
    good: { cls: 'ref-badge-good', label: 'Good' },
    ok: { cls: 'ref-badge-ok', label: 'OK' },
    poor: { cls: 'ref-badge-poor', label: 'Poor' },
    error: { cls: 'ref-badge-poor', label: 'Check failed' },
};

function renderRefList() {
    refList.textContent = '';
    refEntries.forEach((entry, i) => {
        const card = document.createElement('div');
        card.className = 'ref-thumb';

        const img = document.createElement('img');
        img.src = entry.url;
        img.alt = `Reference image: ${entry.file.name}`;

        const meta = document.createElement('div');
        meta.className = 'ref-thumb-meta';

        const name = document.createElement('div');
        name.className = 'ref-name';
        name.textContent = entry.file.name;
        name.title = entry.file.name;

        const badge = document.createElement('span');
        const info = REF_BADGE[entry.rating] || REF_BADGE.checking;
        badge.className = `ref-badge ${info.cls}`.trim();
        badge.textContent = info.label;
        if (entry.detail) badge.title = entry.detail;

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'ref-thumb-remove';
        removeBtn.textContent = 'Remove';
        removeBtn.setAttribute('aria-label', `Remove reference ${entry.file.name}`);
        removeBtn.addEventListener('click', () => removeRefAt(i));

        meta.append(name, badge, document.createElement('br'), removeBtn);
        card.append(img, meta);
        refList.appendChild(card);
    });
}

async function validateReferenceEntry(entry) {
    const fd = new FormData();
    fd.append('reference', entry.file);
    try {
        const r = await fetch('/api/validate-reference', { method: 'POST', body: fd });
        const data = await r.json();
        if (!r.ok || data.error) {
            entry.rating = 'error';
            entry.detail = data.error || 'Validation failed.';
        } else {
            entry.rating = data.rating;
            const lines = [
                `${data.width}×${data.height}, mean chroma ${Number(data.saturation).toFixed(1)}`,
                ...(data.messages || []),
                ...(data.suggestions || []).map(s => `Suggestion: ${s}`),
            ];
            entry.detail = lines.join('\n');
        }
    } catch (err) {
        entry.rating = 'error';
        entry.detail = 'Validation failed: ' + err.message;
    }
    // Entry may have been removed while the request was in flight.
    if (refEntries.includes(entry)) renderRefList();
}

// ── Upload button state ─────────────────────────────────────────────────────

function updateUploadButtonState() {
    const mode = getSelectedMode();
    let hint = '';
    if (!selectedFile) {
        hint = 'Select a PDF to continue';
    } else if (mode === 'reference' && refEntries.length === 0) {
        hint = 'Reference mode needs at least one reference image';
    }
    uploadBtn.disabled = !!hint;
    submitHint.textContent = hint;
    submitHint.hidden = !hint;
}

// ── Time estimate ───────────────────────────────────────────────────────────

function getQualityKey() {
    const r = document.querySelector('input[name="quality"]:checked');
    return r ? r.value : 'standard';
}

function updateTimeEstimate() {
    const key = getQualityKey();
    const preset = (QUALITY_PRESETS || []).find(q => q.key === key);
    const out = document.getElementById('timeEstimate');
    if (!preset || !out) return;
    out.textContent = `Estimated ~${preset.seconds_per_page_estimate}s per page on GPU.`;
}

document.querySelectorAll('input[name="quality"]').forEach(r => {
    r.addEventListener('change', updateTimeEstimate);
});

updateTimeEstimate();

// ── GPU Detection (detailed VRAM box) ───────────────────────────────────────

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
            infoBox.hidden = false;
            infoBox.innerHTML = '<strong>No GPU detected.</strong><br><span class="text-dim">CUDA is not available. Using CPU mode.</span>';
            status.textContent = '';
            btn.disabled = false;
            return;
        }

        const gpu = data.gpus[0];
        const recText = data.recommended === 'cuda'
            ? '<span class="text-success">Recommended: GPU</span>'
            : '<span class="text-warning">Recommended: CPU</span> (low VRAM)';

        infoBox.hidden = false;
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

        gpuLabel.hidden = false;
        if (data.recommended === 'cuda') {
            document.querySelector('input[name="device"][value="cuda"]').checked = true;
        }
        status.textContent = '';
    } catch (err) {
        status.textContent = 'Detection failed';
        infoBox.hidden = false;
        infoBox.innerHTML = '<span class="text-dim">Could not detect GPU. Using CPU mode.</span>';
    }
    btn.disabled = false;
});

// ── Upload (XHR for real byte progress) ─────────────────────────────────────

const uploadProgress = document.getElementById('uploadProgress');
const uploadBar = document.getElementById('uploadBar');
const uploadFill = document.getElementById('uploadFill');
const uploadStatus = document.getElementById('uploadStatus');

function setUploadProgress(pct) {
    uploadBar.classList.remove('indeterminate');
    uploadFill.style.width = pct + '%';
    uploadBar.setAttribute('aria-valuenow', String(Math.round(pct)));
}

function setUploadIndeterminate() {
    uploadFill.style.width = '';
    uploadBar.classList.add('indeterminate');
    uploadBar.removeAttribute('aria-valuenow');
}

function uploadFailed(message) {
    uploadBar.classList.remove('indeterminate');
    uploadStatus.textContent = message;
    uploadBtn.disabled = false;
}

function sendUpload(formData) {
    return new Promise(resolve => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/upload');
        xhr.upload.onprogress = e => {
            if (!e.lengthComputable) return;
            const pct = Math.round((e.loaded / e.total) * 100);
            if (pct >= 100) {
                setUploadIndeterminate();
                uploadStatus.textContent = 'Extracting pages…';
            } else {
                setUploadProgress(pct);
                uploadStatus.textContent = `Uploading… ${pct}%`;
            }
        };
        xhr.upload.onload = () => {
            setUploadIndeterminate();
            uploadStatus.textContent = 'Extracting pages…';
        };
        xhr.onload = () => resolve(xhr);
        xhr.onerror = () => resolve(null);
        xhr.send(formData);
    });
}

uploadBtn.addEventListener('click', async () => {
    if (!selectedFile) return;
    uploadBtn.disabled = true;

    const formData = new FormData();
    formData.append('file', selectedFile);

    const mode = getSelectedMode();
    formData.append('mode', mode);

    if (mode === 'reference') {
        for (const entry of refEntries) {
            formData.append('references', entry.file);
        }
    }

    const style = document.querySelector('input[name="style"]:checked');
    if (style) formData.append('style', style.value);
    const quality = document.querySelector('input[name="quality"]:checked');
    if (quality) formData.append('quality', quality.value);
    const styleLabel = document.querySelector('input[name="style_label"]:checked');
    if (styleLabel) formData.append('style_label', styleLabel.value);

    const device = document.querySelector('input[name="device"]:checked');
    if (device) formData.append('device', device.value);

    if (document.getElementById('cmykExport').checked) {
        formData.append('cmyk_export', '1');
    }

    const llmDirector = document.getElementById('llmDirector');
    formData.append('llm_director',
        (llmDirector && llmDirector.checked && !llmDirector.disabled) ? '1' : '0');

    uploadProgress.hidden = false;
    setUploadProgress(0);
    uploadStatus.textContent = 'Uploading… 0%';

    const xhr = await sendUpload(formData);

    if (!xhr) {
        uploadFailed('Upload failed — check your connection and try again.');
        return;
    }

    if (xhr.status === 413) {
        uploadFailed('File exceeds the 200 MB limit');
        return;
    }

    let data = null;
    try {
        data = JSON.parse(xhr.responseText);
    } catch (err) {
        data = null;
    }

    if (!data) {
        uploadFailed('The server returned an unexpected response. Please try again.');
        return;
    }
    if (xhr.status >= 400 || data.error) {
        uploadFailed('Error: ' + (data.error || 'Upload failed. Please try again.'));
        return;
    }

    uploadBar.classList.remove('indeterminate');
    setUploadProgress(90);
    uploadStatus.textContent =
        `Found ${data.page_count} pages. Starting colorization…`;

    // Verify colorization actually started before redirecting.
    try {
        const res = await fetch(`/api/colorize/${data.job_id}`, { method: 'POST' });
        let cData = null;
        try { cData = await res.json(); } catch (err) { cData = null; }
        if (!res.ok || !cData || !cData.ok) {
            uploadFailed('Error: ' + ((cData && cData.error) || 'Could not start colorization. Please try again.'));
            return;
        }
        setUploadProgress(100);
        window.location.href = `/processing/${data.job_id}`;
    } catch (err) {
        uploadFailed('Could not start colorization: ' + err.message);
    }
});
