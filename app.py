"""ColorComic Flask backend.

The module is safe to import from desktop launchers and packaging tools:
importing it does not start Flask, download model weights, or load ML models.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import uuid

from config import Config


jobs = {}
job_queues = {}
logger = logging.getLogger(__name__)

_model_manager = None
_post_processor = None
_runtime_lock = threading.Lock()
_torch_runtime_configured = False


class ColorizationStepError(RuntimeError):
    """Wrap a colorization failure with the user-visible processing step."""

    def __init__(self, step: str, message: str):
        self.step = step
        super().__init__(f"{step} failed: {message}")


def _read_image_or_raise(path: str, step: str, label: str, cv2_module=None):
    if cv2_module is None:
        import cv2 as cv2_module

    image = cv2_module.imread(path)
    if image is None:
        raise ColorizationStepError(
            step,
            f"OpenCV could not read {label} image at {path!r}. "
            "Check that the file exists and is a supported image format.",
        )
    return image


def _step_error_message(exc: Exception, fallback_step: str) -> str:
    if isinstance(exc, ColorizationStepError):
        return str(exc)
    return f"{fallback_step} failed: {exc}"


def _model_progress_message(mode: str, message: str) -> str:
    normalized = message.replace("[MangaNinja]", "").strip()
    lowered = normalized.lower()
    if mode == "reference":
        if "downloading manganinja" in lowered:
            return "Downloading MangaNinja weights..."
        if "loading sd 1.5" in lowered:
            return "Loading SD 1.5 components..."
        return "Loading Reference mode model..."
    if "downloading" in lowered:
        return "Downloading auto colorization model..."
    if "extracting" in lowered:
        return "Preparing auto colorization model..."
    return "Loading auto colorization model..."


def _model_progress_callback(job, event_queue: queue.Queue, mode: str):
    last_step = {"value": None}

    def callback(message: str) -> None:
        print(message)
        step = _model_progress_message(mode, message)
        if step == last_step["value"]:
            return
        last_step["value"] = step
        job.current_step = step
        event_queue.put({"status": "model", "step": step})

    return callback


def _runtime_output_pdf_path(job_id: str) -> str:
    return os.path.join(Config.OUTPUT_FOLDER, job_id, "colorized.pdf")


def _download_pdf_path(job_id: str) -> str | None:
    job = jobs.get(job_id)
    candidates = []
    if job and job.output_pdf:
        candidates.append(job.output_pdf)
    candidates.append(_runtime_output_pdf_path(job_id))

    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def _sanitize_windows_filename_stem(name: str) -> str:
    invalid_chars = '<>:"/\\|?*'
    sanitized = []
    for char in name:
        if char in invalid_chars or ord(char) < 32:
            sanitized.append("_")
        else:
            sanitized.append(char)
    result = "".join(sanitized).strip(" .")
    while "__" in result:
        result = result.replace("__", "_")

    reserved_names = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if not result or result.upper() in reserved_names:
        return ""
    return result[:180].rstrip(" .")


def _download_pdf_name(job_id: str) -> str:
    job = jobs.get(job_id)
    if job and getattr(job, "pdf_path", None):
        original_name = os.path.basename(job.pdf_path)
        original_stem = os.path.splitext(original_name)[0]
        safe_stem = _sanitize_windows_filename_stem(original_stem)
        if safe_stem:
            return f"{safe_stem}-colorized.pdf"
    return "colorized.pdf"


def _configure_torch_runtime():
    """Enable Torch runtime tuning without loading any model weights."""
    global _torch_runtime_configured
    if _torch_runtime_configured:
        return
    import torch

    torch.backends.cudnn.benchmark = True
    _torch_runtime_configured = True


def get_model_manager():
    """Return the lazy model manager without preloading a colorizer."""
    global _model_manager
    if _model_manager is None:
        with _runtime_lock:
            if _model_manager is None:
                _configure_torch_runtime()
                from core.model_manager import ModelManager

                _model_manager = ModelManager(device=Config.ML_DEVICE)
    return _model_manager


def get_post_processor():
    """Return the post-processing pipeline, loading only lightweight wrappers."""
    global _post_processor
    if _post_processor is None:
        with _runtime_lock:
            if _post_processor is None:
                from core.postprocessor import PostProcessor

                upscaler = None
                if Config.POSTPROCESS_UPSCALE:
                    from core.upscaler import Upscaler

                    upscaler = Upscaler(
                        model_path=Config.ESRGAN_MODEL_PATH,
                        model_url=Config.ESRGAN_MODEL_URL,
                        scale=Config.ESRGAN_SCALE,
                        tile=Config.ESRGAN_TILE,
                        device=Config.ML_DEVICE,
                    )

                _post_processor = PostProcessor(
                    l_channel=Config.POSTPROCESS_L_CHANNEL,
                    guided_filter=Config.POSTPROCESS_GUIDED_FILTER,
                    upscale=Config.POSTPROCESS_UPSCALE,
                    upscaler=upscaler,
                )
    return _post_processor


def _probe_device_summary():
    """Return best-effort device info without touching model weights."""
    try:
        import torch
    except Exception:
        return False, Config.ML_DEVICE

    cuda_available = torch.cuda.is_available()
    if Config.ML_DEVICE == "auto":
        current_device = "cuda" if cuda_available else "cpu"
    else:
        current_device = Config.ML_DEVICE
    return cuda_available, current_device


def _model_status_payload():
    manager = _model_manager
    cuda_available, current_device = _probe_device_summary()
    current_mode = None
    if manager is not None:
        current_mode = manager.current_mode
        current_device = manager.device_name
        cuda_available = manager.cuda_available

    return {
        "model_loaded": current_mode is not None,
        "initialized": manager is not None,
        "device": current_device,
        "cuda_available": cuda_available,
        "current_mode": current_mode,
    }


def create_app():
    """Create and configure the Flask application."""
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

    load_dotenv()

    app = Flask(__name__)
    app.config.from_object(Config)
    app.secret_key = Config.SECRET_KEY

    @app.route("/")
    def index():
        cuda_available, current_device = _probe_device_summary()
        return render_template(
            "index.html",
            cuda_available=cuda_available,
            current_device=current_device,
        )

    @app.route("/favicon.ico")
    def favicon():
        return send_file(Config.APP_ICON_PATH, mimetype="image/x-icon")

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

    @app.route("/upload", methods=["POST"])
    def upload_pdf():
        from core.pdf_handler import extract_pages, get_page_count
        from models.schemas import JobState

        if "file" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        f = request.files["file"]
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            return jsonify({"error": "Only PDF files are accepted"}), 400

        job_id = str(uuid.uuid4())[:12]
        job_dir = os.path.join(Config.UPLOAD_FOLDER, job_id)
        os.makedirs(job_dir, exist_ok=True)

        pdf_path = os.path.join(job_dir, f.filename)
        f.save(pdf_path)

        page_count = get_page_count(pdf_path)
        pages_dir = os.path.join(job_dir, "pages")
        page_images = extract_pages(pdf_path, pages_dir, dpi=Config.PAGE_DPI)

        style = request.form.get("style", "auto")
        device = request.form.get("device", "auto")
        mode = request.form.get("mode", "auto")

        reference_image_path = None
        if mode == "reference" and "reference" in request.files:
            ref_file = request.files["reference"]
            if ref_file.filename:
                ref_path = os.path.join(
                    job_dir,
                    "reference" + os.path.splitext(ref_file.filename)[1],
                )
                ref_file.save(ref_path)
                reference_image_path = ref_path

        if mode == "reference" and not reference_image_path:
            return jsonify({"error": "Reference mode requires a reference image"}), 400

        job = JobState(
            job_id=job_id,
            pdf_path=pdf_path,
            page_count=page_count,
            page_images=page_images,
            style=style,
            device=device,
            mode=mode,
            reference_image_path=reference_image_path,
        )
        jobs[job_id] = job

        return jsonify({"job_id": job_id, "page_count": page_count})

    @app.route("/pages/<job_id>/<int:page_num>")
    def serve_page(job_id, page_num):
        job = jobs.get(job_id)
        if not job or page_num < 0 or page_num >= len(job.page_images):
            return "Not found", 404
        return send_file(job.page_images[page_num], mimetype="image/png")

    @app.route("/api/preview/<job_id>/<int:page_num>")
    def get_preview(job_id, page_num):
        job = jobs.get(job_id)
        if not job:
            return "Not found", 404
        if page_num < 0 or page_num >= len(job.colorized_images):
            return "Page not colorized yet", 400
        path = job.colorized_images[page_num]
        mime = "image/jpeg" if path.lower().endswith(".jpg") else "image/png"
        return send_file(path, mimetype=mime)

    @app.route("/api/colorize/<job_id>", methods=["POST"])
    def start_colorize(job_id):
        job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404

        job.status = "colorizing"
        job.progress = 0.0
        q = queue.Queue()
        job_queues[job_id] = q

        out_dir = os.path.join(Config.OUTPUT_FOLDER, job_id)
        os.makedirs(out_dir, exist_ok=True)

        def _run():
            current_step = "startup"
            try:
                import cv2
                import torch

                from core.color_consistency import ColorConsistencyManager
                from core.pdf_handler import reassemble_pdf

                current_step = "runtime initialization"
                job.current_step = current_step
                model_manager = get_model_manager()
                post_processor = get_post_processor()

                current_step = "model load"
                job.current_step = current_step
                q.put({"status": "model", "step": _model_progress_message(job.mode, current_step)})
                model_manager.switch_device(job.device)
                colorizer = model_manager.get_colorizer(
                    job.mode,
                    callback=_model_progress_callback(job, q, job.mode),
                )

                ref_image = None
                if job.mode == "reference" and job.reference_image_path:
                    current_step = "reference preprocessing"
                    job.current_step = current_step
                    ref_image = _read_image_or_raise(
                        job.reference_image_path,
                        current_step,
                        "reference",
                        cv2_module=cv2,
                    )

                consistency = ColorConsistencyManager()
                colored_paths = []

                with torch.inference_mode():
                    for i, img_path in enumerate(job.page_images):
                        current_step = f"page {i + 1} image loading"
                        job.current_step = current_step
                        q.put({
                            "page": i,
                            "total": job.page_count,
                            "status": "colorizing",
                            "step": current_step,
                        })

                        image = _read_image_or_raise(
                            img_path,
                            current_step,
                            f"page {i + 1}",
                            cv2_module=cv2,
                        )
                        current_step = f"page {i + 1} colorization"
                        job.current_step = current_step
                        if job.mode == "reference":
                            result = colorizer.colorize(image, reference_image=ref_image)
                        else:
                            result = colorizer.colorize(image)

                        current_step = f"page {i + 1} post-processing"
                        job.current_step = current_step
                        result = post_processor.process(result, image)

                        if job.mode == "auto":
                            current_step = f"page {i + 1} color consistency"
                            job.current_step = current_step
                            if i == 0:
                                consistency.set_reference(result)
                            else:
                                result = consistency.apply(
                                    result,
                                    strength=Config.COLOR_TRANSFER_STRENGTH,
                                )

                        out_path = os.path.join(out_dir, f"colored_{i:04d}.jpg")
                        cv2.imwrite(out_path, result, [cv2.IMWRITE_JPEG_QUALITY, 85])
                        colored_paths.append(out_path)
                        job.colorized_images.append(out_path)

                        job.progress = (i + 1) / job.page_count
                        q.put({
                            "page": i,
                            "total": job.page_count,
                            "status": "done_page",
                            "step": current_step,
                        })

                current_step = "PDF export"
                job.current_step = current_step
                output_pdf = os.path.join(out_dir, "colorized.pdf")
                reassemble_pdf(colored_paths, output_pdf, job.pdf_path)
                job.output_pdf = output_pdf
                job.status = "done"
                q.put({"done": True, "download_url": f"/api/download/{job_id}"})
            except Exception as e:
                if job.mode == "reference":
                    logger.exception(
                        "Reference mode colorization failed for job %s during %s",
                        job_id,
                        current_step,
                    )
                else:
                    logger.exception(
                        "Colorization failed for job %s during %s",
                        job_id,
                        current_step,
                    )
                job.status = "error"
                job.current_step = current_step
                q.put({
                    "error": _step_error_message(e, current_step),
                    "step": current_step,
                    "done": True,
                })
            finally:
                job_queues.pop(job_id, None)

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({"ok": True})

    @app.route("/api/colorize/<job_id>/stream")
    def stream_colorize(job_id):
        def generate():
            q = job_queues.get(job_id)
            if not q:
                yield f"data: {json.dumps({'error': 'No active job', 'done': True})}\n\n"
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

    @app.route("/api/download/<job_id>")
    def download_pdf(job_id):
        output_pdf = _download_pdf_path(job_id)
        if not output_pdf:
            return "Not ready", 404
        return send_file(output_pdf, as_attachment=True, download_name=_download_pdf_name(job_id))

    @app.route("/api/health")
    def health():
        return jsonify({"ok": True, "service": "ColorComic"})

    @app.route("/api/status")
    def model_status():
        return jsonify(_model_status_payload())

    @app.route("/api/gpu-info")
    def gpu_info():
        import torch

        if not torch.cuda.is_available():
            return jsonify({"available": False})

        gpu_count = torch.cuda.device_count()
        gpus = []
        for i in range(gpu_count):
            props = torch.cuda.get_device_properties(i)
            mem_total = round(props.total_memory / (1024**3), 1)
            mem_used = round(torch.cuda.memory_allocated(i) / (1024**3), 2)
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

    return app


def run_dev_server():
    """Run the Flask development server for local development."""
    create_app().run(debug=True, port=5000, threaded=True, use_reloader=False)


if __name__ == "__main__":
    run_dev_server()
