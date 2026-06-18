"""ColorComic Flask backend.

The module is safe to import from desktop launchers and packaging tools:
importing it does not start Flask, download model weights, or load ML models.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import uuid

from config import Config


jobs = {}
job_queues = {}

_model_manager = None
_post_processor = None
_runtime_lock = threading.Lock()
_torch_runtime_configured = False


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
            try:
                import cv2
                import torch

                from core.color_consistency import ColorConsistencyManager
                from core.pdf_handler import reassemble_pdf

                model_manager = get_model_manager()
                post_processor = get_post_processor()

                model_manager.switch_device(job.device)
                colorizer = model_manager.get_colorizer(job.mode)

                ref_image = None
                if job.mode == "reference" and job.reference_image_path:
                    ref_image = cv2.imread(job.reference_image_path)

                consistency = ColorConsistencyManager()
                colored_paths = []

                with torch.inference_mode():
                    for i, img_path in enumerate(job.page_images):
                        q.put({"page": i, "total": job.page_count, "status": "colorizing"})

                        image = cv2.imread(img_path)
                        if job.mode == "reference":
                            result = colorizer.colorize(image, reference_image=ref_image)
                        else:
                            result = colorizer.colorize(image)

                        result = post_processor.process(result, image)

                        if job.mode == "auto":
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
                        q.put({"page": i, "total": job.page_count, "status": "done_page"})

                output_pdf = os.path.join(out_dir, "colorized.pdf")
                reassemble_pdf(colored_paths, output_pdf, job.pdf_path)
                job.output_pdf = output_pdf
                job.status = "done"
                q.put({"done": True})
            except Exception as e:
                job.status = "error"
                job.current_step = str(e)
                q.put({"error": str(e), "done": True})
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
        job = jobs.get(job_id)
        if not job or not job.output_pdf:
            return "Not ready", 404
        return send_file(job.output_pdf, as_attachment=True, download_name="colorized.pdf")

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
