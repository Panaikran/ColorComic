"""ColorComic — Flask application for B&W comic PDF colorization."""

import json
import logging
import logging.handlers
import os
import queue
import shutil
import sys
import threading
import time
import traceback
import uuid

import cv2
import numpy as np
import torch
from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from config import Config
from core.character_memory import CharacterMemory
from core.color_consistency import ColorConsistencyManager
from core.cover_detector import detect_anchor_page
from core.guided_colorist import GuidedColorist
from core.model_manager import ModelManager
from core.model_downloader import ensure_models_downloaded
from core.output_writer import write_image, write_cmyk_tiff, write_preview
from core.paint_bucket import flood_recolor
from core.pdf_handler import extract_pages, get_page_count, reassemble_pdf
from core.postprocessor import PostProcessor
from core.presets import (
    all_qualities_json,
    all_styles_json,
    get_quality,
    get_style,
)
from core.quality_score import evaluate as score_page
from core.reference_validator import validate as validate_reference
from core.upscaler import Upscaler, get_shared_upscaler
from models.schemas import JobState, PageQualityRecord

load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────
# Errors and warnings are appended to logs/colorcomic.log with full
# traceback so we can post-mortem without scrolling the terminal.
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "colorcomic.log")

_log_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
_file_handler = logging.handlers.RotatingFileHandler(
    LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(_log_formatter)

_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setLevel(logging.INFO)
_stream_handler.setFormatter(_log_formatter)

# Root at INFO — third-party DEBUG spam (PIL emits several records per image
# save) otherwise lands as synchronous file I/O inside the per-page hot path.
logging.basicConfig(level=logging.INFO, handlers=[_file_handler, _stream_handler])
log = logging.getLogger("colorcomic")
log.setLevel(logging.DEBUG)
log.info("=== ColorComic starting; log file: %s ===", LOG_PATH)


def _excepthook(exc_type, exc_value, exc_tb):
    log.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))


sys.excepthook = _excepthook


def _thread_excepthook(args):
    log.error(
        "Uncaught thread exception in %s",
        args.thread.name if args.thread else "<unknown>",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


threading.excepthook = _thread_excepthook

# Enable cudnn autotuner for consistent input sizes
torch.backends.cudnn.benchmark = True

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY


@app.errorhandler(Exception)
def _flask_log_unhandled(exc):
    """Log any unhandled exception from a Flask route (with traceback)."""
    log.error("Unhandled exception in route %s: %s",
              request.path if request else "<no-request>", exc, exc_info=True)
    raise exc  # let Flask continue with its normal error response


jobs: dict[str, JobState] = {}
job_queues: dict[str, queue.Queue] = {}
job_guides: dict[str, GuidedColorist] = {}  # per-job color scripts (auto mode)

# One GPU job at a time — concurrent pipelines thrash VRAM and halve both
_job_semaphore = threading.Semaphore(1)

# Retention for finished jobs' upload/output dirs (seconds)
_JOB_TTL_SECONDS = int(os.environ.get("COLORCOMIC_JOB_TTL", str(24 * 3600)))

for folder in (Config.UPLOAD_FOLDER, Config.OUTPUT_FOLDER):
    os.makedirs(folder, exist_ok=True)


# ── Load ML model at startup ────────────────────────────────────────────────

print("Checking model weights...")
ensure_models_downloaded(Config.WEIGHTS_DIR, callback=print)

print("Initializing model manager...")
model_manager = ModelManager(device=Config.ML_DEVICE)
model_manager.get_colorizer("auto")


# ── Helpers ─────────────────────────────────────────────────────────────────


def _read_image(path: str) -> np.ndarray:
    """Robust image read: supports 16-bit, 4-channel, and odd formats."""
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Cannot read image: {path}")
    # Normalize dtype FIRST — a 2-D uint16 image must not escape as 16-bit BGR
    if img.dtype == np.uint16:
        img = (img.astype(np.float32) / 257.0).clip(0, 255).astype(np.uint8)
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    return img


def _friendly_error(exc: Exception) -> str:
    """Map raw exceptions to actionable, user-facing messages."""
    msg = str(exc) or exc.__class__.__name__
    low = msg.lower()
    if "out of memory" in low:
        return ("The GPU ran out of memory — try the Draft quality preset "
                "or switch the device to CPU and retry.")
    if "cannot read image" in low or "no such file" in low:
        return "A page image could not be read — try re-uploading the PDF."
    if "connection" in low or "timed out" in low or "timeout" in low:
        return ("Network problem while calling the colorization API — "
                "check your connection and try again.")
    if "openrouter" in low and "401" in msg:
        return "OpenRouter rejected the API key — check OPENROUTER_API_KEY."
    return msg[:300]


def _friendly_job_error(exc: Exception) -> str:
    friendly = _friendly_error(exc)
    log.debug("raw job error: %s", exc)
    return friendly


def _bump_version(job: JobState, page_num: int) -> int:
    v = job.page_versions.get(page_num, 0) + 1
    job.page_versions[page_num] = v
    return v


def _preview_path_for(out_path: str) -> str:
    base, _ = os.path.splitext(out_path)
    return base + ".preview.jpg"


def _prev_path_for(out_path: str) -> str:
    base, ext = os.path.splitext(out_path)
    return base + ".prev" + ext


def _write_outputs(out_path: str, image_bgr: np.ndarray) -> None:
    """Refresh the downscaled preview derivative for an output image."""
    try:
        write_preview(_preview_path_for(out_path), image_bgr)
    except Exception as exc:
        log.warning("preview write failed for %s: %s", out_path, exc)


def _build_post_processor(quality_key: str, style_key: str) -> tuple[PostProcessor, Upscaler | None]:
    """Build a post-processor + (optional, process-shared) upscaler."""
    q = get_quality(quality_key)
    s = get_style(style_key)

    upscaler = None
    if q.use_upscale:
        # Shared singleton — a fresh Upscaler per job/retry re-reads the
        # Real-ESRGAN weights from disk and re-uploads them to the GPU
        upscaler = get_shared_upscaler(
            model_path=Config.ESRGAN_MODEL_PATH,
            model_url=Config.ESRGAN_MODEL_URL,
            scale=Config.ESRGAN_SCALE,
            tile=Config.ESRGAN_TILE,
            device=Config.ML_DEVICE,
        )

    pp = PostProcessor(
        l_channel=Config.POSTPROCESS_L_CHANNEL,
        guided_filter=Config.POSTPROCESS_GUIDED_FILTER,
        upscale=q.use_upscale,
        upscaler=upscaler,
        neutral_preservation=Config.NEUTRAL_PRESERVATION,
        saturation_boost=s.saturation_boost,
        guided_filter_radius=s.guided_filter_radius,
        guided_filter_eps=s.guided_filter_eps,
        hard_masks=Config.POSTPROCESS_HARD_MASKS,
        skin_correction=Config.SKIN_TONE_CORRECTION,
        style=s,
    )
    return pp, upscaler


# ── Background job cleanup ──────────────────────────────────────────────────


def _cleanup_stale_jobs():
    """Evict finished jobs (and their upload/output dirs) after the TTL."""
    while True:
        time.sleep(1800)
        now = time.time()
        for job_id, job in list(jobs.items()):
            if job.status not in ("done", "error", "cancelled"):
                continue
            if not job.finished_at or now - job.finished_at < _JOB_TTL_SECONDS:
                continue
            jobs.pop(job_id, None)
            job_queues.pop(job_id, None)
            job_guides.pop(job_id, None)
            for root in (Config.UPLOAD_FOLDER, Config.OUTPUT_FOLDER):
                path = os.path.join(root, job_id)
                shutil.rmtree(path, ignore_errors=True)
            log.info("evicted stale job %s", job_id)


threading.Thread(target=_cleanup_stale_jobs, daemon=True,
                 name="job-cleanup").start()


# ── Pages ────────────────────────────────────────────────────────────────────


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.route("/")
def index():
    return render_template(
        "index.html",
        cuda_available=model_manager.cuda_available,
        current_device=model_manager.device_name,
        styles=all_styles_json(),
        qualities=all_qualities_json(),
        llm_director_default=Config.LLM_DIRECTOR,
        llm_key_present=bool(os.environ.get("OPENROUTER_API_KEY")),
    )


@app.route("/preview/<job_id>")
def preview_view(job_id):
    job = jobs.get(job_id)
    if not job:
        return redirect(url_for("index"))
    return render_template("preview.html", job=job)


@app.route("/processing/<job_id>")
def processing_view(job_id):
    job = jobs.get(job_id)
    if not job:
        return redirect(url_for("index"))
    return render_template("processing.html", job=job)


# ── API: Reference validator (pre-upload) ───────────────────────────────────


@app.route("/api/validate-reference", methods=["POST"])
def api_validate_reference():
    if "reference" not in request.files:
        return jsonify({"error": "No reference uploaded"}), 400
    f = request.files["reference"]
    blob = f.read()
    if not blob:
        return jsonify({"error": "Empty file"}), 400
    arr = np.frombuffer(blob, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return jsonify({"error": "Could not decode image"}), 400
    verdict = validate_reference(img)
    return jsonify(verdict.to_json())


# ── API: Upload ──────────────────────────────────────────────────────────────


def _extract_job_pages(job: JobState, pdf_path: str, pages_dir: str):
    """Background page extraction + anchor detection (runs off-request)."""
    try:
        job.page_images = extract_pages(
            pdf_path, pages_dir, dpi=Config.PAGE_DPI,
            should_stop=lambda: job.cancel_requested,
        )
        if job.cancel_requested:
            log.info("job %s: extraction aborted by cancel", job.job_id)
            return
        job.anchor_page_index = detect_anchor_page(job.page_images)
        # A cancelled/failed job must not be flipped back to "ready"
        if job.status == "extracting":
            job.status = "ready"
        log.info("job %s: extracted %d pages (anchor=%d)",
                 job.job_id, len(job.page_images), job.anchor_page_index)
    except Exception as exc:
        log.error("job %s: extraction failed: %s", job.job_id, exc, exc_info=True)
        job.status = "error"
        job.error = _friendly_job_error(exc)
        job.finished_at = time.time()


@app.route("/upload", methods=["POST"])
def upload_pdf():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename or not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are accepted"}), 400

    style_label = request.form.get("style_label", "auto")  # legacy: manga/western/auto
    style = request.form.get("style", Config.DEFAULT_STYLE)
    quality = request.form.get("quality", Config.DEFAULT_QUALITY)
    device = request.form.get("device", "auto")
    mode = request.form.get("mode", "auto")
    cmyk_export = request.form.get("cmyk_export", "0") == "1"
    llm_director = request.form.get(
        "llm_director", "1" if Config.LLM_DIRECTOR else "0") == "1"

    if mode not in {"auto", "reference", "llm"}:
        return jsonify({"error": f"Unknown colorization mode: {mode}"}), 400

    if mode == "llm" and not os.environ.get("OPENROUTER_API_KEY"):
        return jsonify({
            "error": "LLM mode requires OPENROUTER_API_KEY in your environment"
        }), 400

    job_id = str(uuid.uuid4())[:12]
    job_dir = os.path.join(Config.UPLOAD_FOLDER, job_id)
    os.makedirs(job_dir, exist_ok=True)

    pdf_path = os.path.join(job_dir, f.filename)
    f.save(pdf_path)

    page_count = get_page_count(pdf_path)  # cheap — no rasterization

    # Collect references — multi-ref list takes precedence
    reference_paths: list[str] = []
    if mode == "reference":
        ref_files = request.files.getlist("references")
        if ref_files:
            for i, rf in enumerate(ref_files):
                if not rf.filename:
                    continue
                ext = os.path.splitext(rf.filename)[1] or ".png"
                rp = os.path.join(job_dir, f"reference_{i}{ext}")
                rf.save(rp)
                reference_paths.append(rp)
        elif "reference" in request.files:
            rf = request.files["reference"]
            if rf.filename:
                ext = os.path.splitext(rf.filename)[1] or ".png"
                rp = os.path.join(job_dir, f"reference{ext}")
                rf.save(rp)
                reference_paths.append(rp)

        if not reference_paths:
            return jsonify({"error": "Reference mode requires a reference image"}), 400

    job = JobState(
        job_id=job_id,
        pdf_path=pdf_path,
        page_count=page_count,
        page_images=[],
        style=style,
        style_label=style_label,
        quality=quality,
        device=device,
        mode=mode,
        reference_image_path=reference_paths[0] if reference_paths else None,
        reference_image_paths=reference_paths,
        anchor_page_index=0,
        llm_director=llm_director,
        cmyk_export_requested=cmyk_export,
        status="extracting",
    )
    jobs[job_id] = job

    # 300-DPI rasterization of a whole book takes minutes — never block the
    # upload response on it
    pages_dir = os.path.join(job_dir, "pages")
    threading.Thread(
        target=_extract_job_pages, args=(job, pdf_path, pages_dir),
        daemon=True, name=f"extract-{job_id}",
    ).start()

    return jsonify({
        "job_id": job_id,
        "page_count": page_count,
        "status": job.status,
    })


# ── API: Serve page images ──────────────────────────────────────────────────


@app.route("/pages/<job_id>/<int:page_num>")
def serve_page(job_id, page_num):
    job = jobs.get(job_id)
    if not job or page_num < 0 or page_num >= len(job.page_images):
        return "Not found", 404
    resp = send_file(job.page_images[page_num], mimetype="image/png")
    # Originals never change — let the browser cache them
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


# ── API: Preview (serve pre-computed colorized images) ───────────────────────


@app.route("/api/preview/<job_id>/<int:page_num>")
def get_preview(job_id, page_num):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if (page_num < 0 or page_num >= len(job.colorized_images)
            or not job.colorized_images[page_num]):
        return jsonify({"error": "Page not colorized yet"}), 400
    path = job.colorized_images[page_num]

    # ?w= requests the downscaled preview derivative (thumbnails, progress)
    if request.args.get("w"):
        preview = _preview_path_for(path)
        if not os.path.exists(preview):
            try:
                _write_outputs(path, _read_image(path))
            except Exception:
                preview = None
        if preview and os.path.exists(preview):
            return send_file(preview, mimetype="image/jpeg")

    if path.lower().endswith(".png"):
        mime = "image/png"
    elif path.lower().endswith((".jpg", ".jpeg")):
        mime = "image/jpeg"
    else:
        mime = "application/octet-stream"
    return send_file(path, mimetype=mime)


# ── Helper: colorize a single page given current job state ─────────────────


def _colorize_one(job: JobState, colorizer, page_index: int,
                  pp: PostProcessor,
                  consistency: ColorConsistencyManager,
                  characters: CharacterMemory | None,
                  ref_images: list[np.ndarray] | None,
                  style_key: str | None = None,
                  quality_key: str | None = None,
                  guided: GuidedColorist | None = None) -> str:
    """Colorize one page and return the output path.

    ``style_key`` / ``quality_key`` override the job presets for this call
    (used by per-page retry) without mutating shared job state.
    """
    q = get_quality(quality_key or job.quality)
    s = get_style(style_key or job.style)

    img_path = job.page_images[page_index]
    image = _read_image(img_path)

    # Guided coloring: segment + CLIP-label the page and turn the job's
    # color script into sparse hints for mc-v2's hint channel
    hint_points = None
    if guided is not None and job.mode == "auto":
        try:
            hint_points = guided.hints_for_page(image) or None
        except Exception as exc:
            log.warning("[guided] page %s hints skipped: %s", page_index, exc)

    if job.mode == "reference":
        result = colorizer.colorize(
            image,
            reference_images=ref_images,
            num_inference_steps=int(s.diffusion_steps * q.diffusion_step_mult),
            refine_pass=q.refine_pass,
        )
    elif job.mode == "llm":
        result = colorizer.colorize(
            image,
            style_label=job.style_label,
            style_prompt=f"{s.label}: {s.description}",
            reference_images=ref_images,
        )
    else:
        result = colorizer.colorize(
            image,
            size=q.model_size,
            denoise_sigma=s.denoise_sigma,
            tiled=q.tiled_inference,
            tile_size=q.tile_size,
            tile_overlap=q.tile_overlap,
            per_panel=q.per_panel,
            panel_style="manga" if job.style_label == "manga" else "western",
            deherron=Config.DEHERRON_SCREENTONES,
            deherron_strength=Config.DEHERRON_STRENGTH,
            hint_points=hint_points,
        )

    # Post-processing
    result = pp.process(result, image, style=s)

    # Cross-page color consistency (auto mode only — reference mode has the ref)
    if job.mode == "auto":
        if page_index == job.anchor_page_index:
            consistency.set_reference(result)
        elif consistency.has_reference:
            result = consistency.apply(result, strength=Config.COLOR_TRANSFER_STRENGTH)

    # Per-character palette transfer (auto mode only) — never fatal.
    # Faces are detected + embedded ONCE and shared between apply/observe.
    if characters is not None and job.mode == "auto":
        try:
            detections = characters.analyze(result)
            if page_index == job.anchor_page_index:
                characters.observe(result, page_num=page_index,
                                   detections=detections)
            elif detections:
                result = characters.apply(result, page_num=page_index,
                                          strength=Config.CHARACTER_BLEND_STRENGTH,
                                          detections=detections)
                characters.observe(result, page_num=page_index,
                                   detections=detections)
        except Exception as exc:
            log.warning("[character_memory] page %s skipped: %s", page_index, exc)

    # Output (+ downscaled preview derivative for the browser)
    out_dir = os.path.join(Config.OUTPUT_FOLDER, job.job_id)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"colored_{page_index:04d}.{q.output_format}")
    out_path = write_image(out_path, result, fmt=q.output_format,
                           jpeg_quality=q.jpeg_quality, embed_icc=True)
    _write_outputs(out_path, result)

    # Quality score (runs on a downscaled copy internally)
    try:
        score = score_page(result, image)
        record = PageQualityRecord(
            score=score.score,
            issues=score.issues,
            chroma_mean=score.chroma_mean,
            chroma_std=score.chroma_std,
            skin_safety=score.skin_safety,
            bleed_score=score.bleed_score,
        )
        while len(job.page_quality) <= page_index:
            job.page_quality.append(PageQualityRecord())
        job.page_quality[page_index] = record
    except Exception as exc:
        log.warning("[quality] page %s skipped: %s", page_index, exc)

    return out_path


def _set_page_output(job: JobState, page_index: int, out_path: str) -> None:
    while len(job.colorized_images) <= page_index:
        job.colorized_images.append("")
    job.colorized_images[page_index] = out_path


# ── API: Colorize (ML pipeline) ─────────────────────────────────────────────


def _wait_for_extraction(job: JobState, q: queue.Queue) -> bool:
    """Block until page extraction finishes. Returns False on failure/cancel."""
    if job.status == "extracting":
        q.put({"status": "extracting"})
    while job.status == "extracting":
        if job.cancel_requested:
            return False
        time.sleep(0.2)
    if job.status == "error":
        q.put({"error": job.error or "Page extraction failed", "done": True})
        return False
    return True


def _colorize_pages_llm(job: JobState, colorizer, order: list[int],
                        pp: PostProcessor, q: queue.Queue) -> None:
    """LLM mode: network-bound — colorize pages concurrently."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    consistency = ColorConsistencyManager()  # unused in llm mode, kept for signature
    max_workers = min(6, max(1, len(order)))

    def _one(i: int) -> tuple[int, str]:
        with torch.inference_mode():
            return i, _colorize_one(job, colorizer, i, pp, consistency, None, None)

    q.put({"status": "colorizing", "page": order[0],
           "processed_count": 0, "total": job.page_count})
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_one, i): i for i in order}
        for fut in as_completed(futures):
            if job.cancel_requested:
                pool.shutdown(wait=False, cancel_futures=True)
                raise _JobCancelled()
            i, out_path = fut.result()  # raises on page failure
            _set_page_output(job, i, out_path)
            job.processed_count += 1
            job.progress = job.processed_count / job.page_count
            quality_record = (
                job.page_quality[i].model_dump()
                if i < len(job.page_quality) else None
            )
            q.put({
                "page": i,
                "total": job.page_count,
                "processed_count": job.processed_count,
                "status": "done_page",
                "quality": quality_record,
            })


class _JobCancelled(Exception):
    pass


@app.route("/api/colorize/<job_id>", methods=["POST"])
def start_colorize(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    # An active queue means a worker is running (possibly still waiting on
    # extraction) — status alone can't tell those apart
    if job.status == "colorizing" or job_id in job_queues:
        return jsonify({"error": "This job is already being colorized"}), 409

    if job.status != "extracting":
        job.status = "colorizing"
    job.progress = 0.0
    job.processed_count = 0
    job.colorized_images = []
    job.page_quality = []
    job.cancel_requested = False
    job.error = None
    q = queue.Queue()
    job_queues[job_id] = q

    def _run():
        try:
            if not _wait_for_extraction(job, q):
                if job.cancel_requested:
                    raise _JobCancelled()
                return  # extraction error already reported

            job.status = "colorizing"

            # One GPU pipeline at a time
            with _job_semaphore:
                if job.cancel_requested:
                    raise _JobCancelled()

                q.put({"status": "loading_model",
                       "message": "Loading colorization model — first use may download weights"})
                model_manager.switch_device(job.device)
                colorizer = model_manager.get_colorizer(job.mode)

                ref_images: list[np.ndarray] | None = None
                if job.mode == "reference" and job.reference_image_paths:
                    ref_images = [_read_image(p) for p in job.reference_image_paths]

                consistency = ColorConsistencyManager()
                characters = (
                    CharacterMemory()
                    if Config.CHARACTER_MEMORY and job.mode == "auto" else None
                )
                pp, _ = _build_post_processor(job.quality, job.style)

                # Guided coloring: build the job's color script once —
                # CLIP labels the anchor page, and (if configured) a
                # text-only LLM refines the palette from that summary
                guided = None
                if job.mode == "auto" and Config.GUIDED_HINTS:
                    try:
                        candidate = GuidedColorist(Config, use_llm=job.llm_director)
                        if candidate.available:
                            anchor_img = _read_image(
                                job.page_images[job.anchor_page_index])
                            candidate.prepare([anchor_img])
                            guided = candidate
                            job_guides[job_id] = guided
                            log.info("guided coloring ready (script: %s)",
                                     (guided.script or {}).get("source"))
                    except Exception as exc:
                        log.warning("guided coloring unavailable: %s", exc)

                # Process anchor page first so consistency / character memory
                # see colors before applying them downstream
                order = [job.anchor_page_index] + [
                    i for i in range(job.page_count) if i != job.anchor_page_index
                ]

                if job.mode == "llm":
                    _colorize_pages_llm(job, colorizer, order, pp, q)
                else:
                    with torch.inference_mode():
                        for i in order:
                            if job.cancel_requested:
                                raise _JobCancelled()
                            q.put({"page": i, "total": job.page_count,
                                   "processed_count": job.processed_count,
                                   "status": "colorizing"})

                            out_path = _colorize_one(
                                job, colorizer, i, pp, consistency, characters,
                                ref_images, guided=guided,
                            )
                            _set_page_output(job, i, out_path)

                            job.processed_count += 1
                            job.progress = job.processed_count / job.page_count
                            quality_record = (
                                job.page_quality[i].model_dump()
                                if i < len(job.page_quality) else None
                            )
                            q.put({
                                "page": i,
                                "total": job.page_count,
                                "processed_count": job.processed_count,
                                "status": "done_page",
                                "quality": quality_record,
                            })

                # Reassemble PDF using page order
                q.put({"status": "assembling"})
                ordered_paths = [job.colorized_images[i] for i in range(job.page_count)
                                 if i < len(job.colorized_images) and job.colorized_images[i]]
                output_pdf = os.path.join(Config.OUTPUT_FOLDER, job_id, "colorized.pdf")
                reassemble_pdf(ordered_paths, output_pdf, job.pdf_path)
                job.output_pdf = output_pdf

                # Optional CMYK TIFF for first page (full book CMYK is heavy;
                # keep this as a sample print-ready export the user can request)
                if job.cmyk_export_requested and ordered_paths:
                    first_img = _read_image(ordered_paths[0])
                    cmyk_path = os.path.join(Config.OUTPUT_FOLDER, job_id, "cmyk_sample.tiff")
                    produced = write_cmyk_tiff(cmyk_path, first_img)
                    if produced:
                        job.output_cmyk = produced

                if characters is not None:
                    job.character_summary = characters.summary()

            job.status = "done"
            job.finished_at = time.time()
            q.put({"done": True})
        except _JobCancelled:
            log.info("colorize-job %s cancelled", job_id)
            job.status = "cancelled"
            job.finished_at = time.time()
            q.put({"cancelled": True, "done": True})
        except Exception as e:
            tb = traceback.format_exc()
            log.error("colorize-job %s failed: %s\n%s", job_id, e, tb)
            job.status = "error"
            job.error = _friendly_job_error(e)
            job.current_step = job.error
            job.finished_at = time.time()
            q.put({"error": job.error, "done": True})
        finally:
            job_queues.pop(job_id, None)

    threading.Thread(target=_run, daemon=True, name=f"colorize-{job_id}").start()
    return jsonify({"ok": True})


@app.route("/api/cancel/<job_id>", methods=["POST"])
def cancel_job(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job.status in ("done", "error", "cancelled"):
        return jsonify({"ok": True, "status": job.status})
    job.cancel_requested = True
    # No worker running (extracting / not yet started) — finalize directly;
    # the extraction thread checks the flag and aborts without touching status
    if job_id not in job_queues:
        job.status = "cancelled"
        job.finished_at = time.time()
    return jsonify({"ok": True, "status": job.status})


@app.route("/api/colorize/<job_id>/stream")
def stream_colorize(job_id):
    def generate():
        q = job_queues.get(job_id)
        if not q:
            # Reconnect after completion — report the terminal state instead
            # of a bogus "No active job" error
            job = jobs.get(job_id)
            if job is None:
                yield f"data: {json.dumps({'error': 'No such job', 'done': True})}\n\n"
            elif job.status == "done":
                yield f"data: {json.dumps({'done': True})}\n\n"
            elif job.status == "error":
                yield f"data: {json.dumps({'error': job.error or 'Job failed', 'done': True})}\n\n"
            elif job.status == "cancelled":
                yield f"data: {json.dumps({'cancelled': True, 'done': True})}\n\n"
            else:
                yield f"data: {json.dumps({'status': job.status})}\n\n"
            return
        while True:
            try:
                event = q.get(timeout=30)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("done"):
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'heartbeat': True})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── API: Per-page retry ─────────────────────────────────────────────────────


@app.route("/api/retry/<job_id>/<int:page_num>", methods=["POST"])
def retry_page(job_id, page_num):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if page_num < 0 or page_num >= job.page_count:
        return jsonify({"error": "Bad page index"}), 400

    body = request.get_json(silent=True) or {}
    style_override = body.get("style") or job.style
    quality_override = body.get("quality") or job.quality
    sat_override = body.get("saturation_boost")
    seed_bump = bool(body.get("seed_bump", True))

    pp, _ = _build_post_processor(quality_override, style_override)
    if sat_override is not None:
        try:
            pp.saturation_boost = float(sat_override)
        except Exception:
            pass

    try:
        colorizer = model_manager.get_colorizer(job.mode)
        ref_images = (
            [_read_image(p) for p in job.reference_image_paths]
            if job.mode == "reference" and job.reference_image_paths else None
        )
        consistency = ColorConsistencyManager()
        if job.colorized_images and job.anchor_page_index < len(job.colorized_images):
            anchor_path = job.colorized_images[job.anchor_page_index]
            if anchor_path and page_num != job.anchor_page_index:
                consistency.set_reference(_read_image(anchor_path))

        characters = None  # don't update memory on a retry

        if seed_bump:
            torch.manual_seed(np.random.randint(1, 1_000_000))

        # Keep the previous file for one-level undo
        old_path = (job.colorized_images[page_num]
                    if page_num < len(job.colorized_images) else "")
        prev_backup = None
        if old_path and os.path.exists(old_path):
            prev_backup = _prev_path_for(old_path)
            shutil.copy2(old_path, prev_backup)

        with torch.inference_mode():
            out_path = _colorize_one(
                job, colorizer, page_num, pp, consistency, characters, ref_images,
                style_key=style_override, quality_key=quality_override,
                guided=job_guides.get(job_id),  # same color script as the run
            )
        _set_page_output(job, page_num, out_path)
        version = _bump_version(job, page_num)
        return jsonify({
            "ok": True,
            "path": f"/api/preview/{job_id}/{page_num}",
            "version": version,
            "can_undo": prev_backup is not None,
        })
    except Exception as exc:
        log.error("retry %s page %s failed: %s", job_id, page_num, exc, exc_info=True)
        return jsonify({"error": _friendly_error(exc)}), 500


# ── API: Paint-bucket touch-up + undo ───────────────────────────────────────


@app.route("/api/touchup/<job_id>/<int:page_num>", methods=["POST"])
def touchup_page(job_id, page_num):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if page_num < 0 or page_num >= len(job.colorized_images):
        return jsonify({"error": "Page not yet colorized"}), 400

    body = request.get_json(silent=True) or {}
    try:
        x = int(body["x"])
        y = int(body["y"])
        color_hex = str(body["color"])
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "Need x, y, color"}), 400
    tolerance = int(body.get("tolerance", 18))
    feather = int(body.get("feather", 3))

    path = job.colorized_images[page_num]
    img = _read_image(path)

    # Keep the previous file for one-level undo — touch-up is destructive
    shutil.copy2(path, _prev_path_for(path))

    new_img, _mask = flood_recolor(img, x, y, color_hex,
                                   tolerance=tolerance, feather=feather)

    fmt = "png" if path.lower().endswith(".png") else "jpg"
    new_path = write_image(path, new_img, fmt=fmt,
                           jpeg_quality=95, embed_icc=True)
    _write_outputs(new_path, new_img)
    job.colorized_images[page_num] = new_path
    version = _bump_version(job, page_num)

    return jsonify({
        "ok": True,
        "path": f"/api/preview/{job_id}/{page_num}",
        "version": version,
        "can_undo": True,
    })


@app.route("/api/undo/<job_id>/<int:page_num>", methods=["POST"])
def undo_page(job_id, page_num):
    """Swap the current page image with its .prev backup (undo/redo toggle)."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if page_num < 0 or page_num >= len(job.colorized_images):
        return jsonify({"error": "Page not yet colorized"}), 400

    path = job.colorized_images[page_num]
    prev = _prev_path_for(path)
    if not path or not os.path.exists(prev):
        return jsonify({"error": "Nothing to undo"}), 400

    tmp = path + ".swap"
    os.replace(path, tmp)
    os.replace(prev, path)
    os.replace(tmp, prev)

    try:
        _write_outputs(path, _read_image(path))
    except Exception:
        pass
    version = _bump_version(job, page_num)
    return jsonify({
        "ok": True,
        "path": f"/api/preview/{job_id}/{page_num}",
        "version": version,
        "can_undo": True,  # swap is symmetric — undo again to redo
    })


# ── API: CMYK export ────────────────────────────────────────────────────────


@app.route("/api/cmyk/<job_id>/<int:page_num>", methods=["POST"])
def export_cmyk(job_id, page_num):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if page_num < 0 or page_num >= len(job.colorized_images):
        return jsonify({"error": "Page not yet colorized"}), 400

    img = _read_image(job.colorized_images[page_num])
    out = os.path.join(
        Config.OUTPUT_FOLDER, job_id, f"cmyk_{page_num:04d}.tiff",
    )
    produced = write_cmyk_tiff(out, img)
    if not produced:
        return jsonify({"error": "CMYK conversion unavailable on this server"}), 500
    return jsonify({
        "ok": True,
        "path": produced,
        "download_url": f"/api/download-cmyk/{job_id}/{page_num}",
    })


# ── API: Quality scores + characters ────────────────────────────────────────


@app.route("/api/job/<job_id>")
def job_info(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "processed_count": job.processed_count,
        "page_count": job.page_count,
        "anchor_page_index": job.anchor_page_index,
        "style": job.style,
        "quality": job.quality,
        "mode": job.mode,
        "current_step": job.current_step,
        "error": job.error,
        "page_quality": [pq.model_dump() for pq in job.page_quality],
        "character_summary": job.character_summary,
        "output_cmyk": job.output_cmyk,
        "page_versions": job.page_versions,
    })


@app.route("/api/presets")
def api_presets():
    return jsonify({
        "styles": all_styles_json(),
        "qualities": all_qualities_json(),
    })


# ── API: Download ────────────────────────────────────────────────────────────


@app.route("/api/download/<job_id>")
def download_pdf(job_id):
    job = jobs.get(job_id)
    if not job or not job.output_pdf:
        return "Not ready", 404
    return send_file(job.output_pdf, as_attachment=True, download_name="colorized.pdf")


@app.route("/api/download-cmyk/<job_id>")
def download_cmyk(job_id):
    job = jobs.get(job_id)
    if not job or not job.output_cmyk:
        return "Not ready", 404
    return send_file(job.output_cmyk, as_attachment=True,
                     download_name="colorized_cmyk.tiff")


@app.route("/api/download-cmyk/<job_id>/<int:page_num>")
def download_cmyk_page(job_id, page_num):
    job = jobs.get(job_id)
    if not job:
        return "Not found", 404
    path = os.path.join(Config.OUTPUT_FOLDER, job_id, f"cmyk_{page_num:04d}.tiff")
    if not os.path.exists(path):
        return "Not ready", 404
    return send_file(path, as_attachment=True,
                     download_name=f"colorized_cmyk_page{page_num + 1}.tiff")


# ── API: Status ──────────────────────────────────────────────────────────────


@app.route("/api/status")
def model_status():
    return jsonify({
        "version": Config.VERSION,
        "model_loaded": True,
        "device": model_manager.device_name,
        "cuda_available": model_manager.cuda_available,
        "current_mode": model_manager.current_mode,
    })


@app.route("/api/gpu-info")
def gpu_info():
    if not torch.cuda.is_available():
        return jsonify({"available": False})

    gpu_count = torch.cuda.device_count()
    gpus = []
    for i in range(gpu_count):
        props = torch.cuda.get_device_properties(i)
        mem_total = round(props.total_memory / (1024 ** 3), 1)
        mem_used = round(torch.cuda.memory_allocated(i) / (1024 ** 3), 2)
        mem_free = round(mem_total - mem_used, 1)
        gpus.append({
            "index": i,
            "name": props.name,
            "vram_total_gb": mem_total,
            "vram_free_gb": mem_free,
            "compute_capability": f"{props.major}.{props.minor}",
            "multi_processors": props.multi_processor_count,
        })

    recommended = "cuda" if gpus and gpus[0]["vram_total_gb"] >= 2 else "cpu"

    return jsonify({
        "available": True,
        "driver": torch.version.cuda,
        "gpu_count": gpu_count,
        "gpus": gpus,
        "recommended": recommended,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True, use_reloader=False)
