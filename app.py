"""ColorComic Flask backend.

The module is safe to import from desktop launchers and packaging tools:
importing it does not start Flask, download model weights, or load ML models.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import queue
import shutil
import sys
import threading
import time
import uuid
from datetime import datetime, timezone

from config import Config
from core.batch_queue import (
    BatchRecord,
    BatchQueueError,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PAUSED,
    STATUS_QUEUED,
    STATUS_RECOVERY_REQUIRED,
    STATUS_RUNNING,
    SingleWorkerBatchRunner,
    create_batch,
    derive_batch_status,
    remove_pending_job,
    reorder_queued_job,
    transition_job,
)
from core.job_history import (
    JobHistoryEntry,
    append_job_history,
    load_job_history,
    remove_job_history_entry,
)
from core.job_timing import JobTiming
from core.diagnostics_bundle import create_diagnostics_bundle
from core.device_detection import detect_device_capabilities, is_official_cpu_build, resolve_compute_device
from core.preflight import PreflightResult, validate_colorize_preflight, validate_runtime_health
from core.preferences import load_preferences, reset_preferences, save_preferences
from core.queue_manifest import (
    QueueBatchRecord,
    QueueJobRecord,
    QueueManifest,
    load_queue_manifest,
    save_queue_manifest,
)


jobs = {}
job_queues = {}
batches = {}
active_batch_runners = {}
logger = logging.getLogger(__name__)

_model_manager = None
_post_processor = None
_runtime_lock = threading.Lock()
_batch_lock = threading.Lock()
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


def _preflight_error_message(errors) -> str:
    messages = [error.message for error in errors]
    if not messages:
        return "ColorComic could not check the files before processing."
    return "; ".join(messages)


def _runtime_health_errors():
    return validate_runtime_health(
        Config.RUNTIME_DIR,
        Config.UPLOAD_FOLDER,
        Config.OUTPUT_FOLDER,
        Config.LOG_DIR,
        Config.CONFIG_DIR,
    )


def _with_runtime_health(preflight):
    runtime_errors = _runtime_health_errors()
    if not runtime_errors:
        return preflight
    return PreflightResult(
        ok=False,
        pdf_path=preflight.pdf_path,
        output_dir=preflight.output_dir,
        page_count=preflight.page_count,
        reference_image_path=preflight.reference_image_path,
        errors=runtime_errors + preflight.errors,
    )


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


def _validate_preferences_update(payload) -> tuple[dict | None, str | None]:
    if not isinstance(payload, dict):
        return None, "Preferences payload must be a JSON object."

    updates = {}
    if "default_mode" in payload:
        if payload["default_mode"] not in ("auto", "reference"):
            return None, "default_mode must be auto or reference."
        updates["default_mode"] = payload["default_mode"]

    if "default_device" in payload:
        if payload["default_device"] != "cpu":
            return None, "default_device must be cpu."
        updates["default_device"] = payload["default_device"]

    if "open_output_folder_after_completion" in payload:
        if not isinstance(payload["open_output_folder_after_completion"], bool):
            return None, "open_output_folder_after_completion must be true or false."
        updates["open_output_folder_after_completion"] = payload["open_output_folder_after_completion"]

    return updates, None


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


def _safe_uploaded_pdf_name(filename: str, fallback_stem: str) -> str:
    original_name = os.path.basename(filename or "")
    original_stem, extension = os.path.splitext(original_name)
    safe_stem = _sanitize_windows_filename_stem(original_stem) or fallback_stem
    if extension.lower() != ".pdf":
        extension = ".pdf"
    return f"{safe_stem}{extension.lower()}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _record_completed_job_history(
    job,
    output_pdf: str,
    history_path: str | None = None,
    batch_id: str | None = None,
) -> bool:
    if not output_pdf or not os.path.isfile(output_pdf):
        return False

    original_filename = os.path.basename(getattr(job, "pdf_path", "")) or "colorized.pdf"
    page_count = getattr(job, "page_count", None)
    if not isinstance(page_count, int):
        page_count = None
    timing_summary = getattr(job, "timing_summary", None)
    if not isinstance(timing_summary, dict):
        timing_summary = None

    entry = JobHistoryEntry(
        job_id=job.job_id,
        original_filename=original_filename,
        mode=getattr(job, "mode", "auto") or "auto",
        completed_at=_utc_now_iso(),
        output_pdf_path=output_pdf,
        page_count=page_count,
        batch_id=batch_id,
        timing_summary=timing_summary,
    )
    try:
        append_job_history(entry, path=history_path)
    except Exception:
        logger.exception("Failed to write job history for job %s", job.job_id)
        return False
    return True


def _is_runtime_output_path(path: str, output_folder: str | None = None) -> bool:
    if not path:
        return False
    output_root = os.path.abspath(output_folder or Config.OUTPUT_FOLDER)
    candidate = os.path.abspath(path)
    try:
        common = os.path.commonpath([output_root, candidate])
    except ValueError:
        return False
    return os.path.normcase(common) == os.path.normcase(output_root)


def _is_runtime_upload_path(path: str) -> bool:
    if not path:
        return False
    upload_root = os.path.abspath(Config.UPLOAD_FOLDER)
    candidate = os.path.abspath(path)
    try:
        common = os.path.commonpath([upload_root, candidate])
    except ValueError:
        return False
    return os.path.normcase(common) == os.path.normcase(upload_root)


def _recovery_input_error(record) -> str | None:
    if not _is_runtime_upload_path(record.pdf_path) or not os.path.isfile(record.pdf_path):
        return "Source PDF is unavailable after restart."
    if len(record.page_images) != record.page_count:
        return "Required extracted pages are unavailable after restart."
    for page_path in record.page_images:
        if not _is_runtime_upload_path(page_path) or not os.path.isfile(page_path):
            return "Required extracted page is unavailable after restart."
    return None


def restore_queue_manifest(path: str | None = None) -> int:
    """Restore manifest-backed queue records without starting any work."""
    manifest = load_queue_manifest(path)
    if manifest is None:
        return 0

    from models.schemas import JobState

    restored = 0
    with _batch_lock:
        for saved_batch in manifest.batches:
            job_statuses = {}
            for record in saved_batch.jobs:
                error = _recovery_input_error(record)
                status = record.status
                if error:
                    status = STATUS_RECOVERY_REQUIRED
                elif status == STATUS_RUNNING:
                    status = STATUS_RECOVERY_REQUIRED
                    error = "Colorization was interrupted by application shutdown."
                elif status not in {STATUS_QUEUED, STATUS_PAUSED, STATUS_FAILED}:
                    status = STATUS_RECOVERY_REQUIRED
                    error = "Queue state requires recovery before it can continue."

                jobs[record.job_id] = JobState(
                    job_id=record.job_id,
                    pdf_path=record.pdf_path,
                    page_count=record.page_count,
                    page_images=list(record.page_images),
                    status=status,
                    error=error or record.error,
                    current_step="recovery" if status == STATUS_RECOVERY_REQUIRED else "",
                    style=record.style,
                    device=record.device,
                    mode=record.mode,
                )
                job_statuses[record.job_id] = status

            batches[saved_batch.batch_id] = BatchRecord(
                batch_id=saved_batch.batch_id,
                job_ids=saved_batch.job_ids,
                job_statuses=job_statuses,
                status=derive_batch_status(job_statuses, started_at=saved_batch.started_at),
                created_at=saved_batch.created_at,
                started_at=saved_batch.started_at,
                completed_at=saved_batch.completed_at,
            )
            restored += 1
    return restored


def _recent_job_payload(entry: JobHistoryEntry) -> dict:
    output_pdf_safe = _is_runtime_output_path(entry.output_pdf_path)
    output_pdf_exists = output_pdf_safe and os.path.isfile(entry.output_pdf_path)
    payload = {
        "job_id": entry.job_id,
        "original_filename": entry.original_filename,
        "mode": entry.mode,
        "completed_at": entry.completed_at,
        "output_pdf_path": entry.output_pdf_path if output_pdf_safe else None,
        "output_pdf_exists": output_pdf_exists,
        "output_pdf_safe": output_pdf_safe,
    }
    if entry.page_count is not None:
        payload["page_count"] = entry.page_count
    if entry.batch_id:
        payload["batch_id"] = entry.batch_id
    return payload


def _batch_counts_payload(counts) -> dict:
    return {
        "queued": counts.queued,
        "paused": counts.paused,
        "running": counts.running,
        "completed": counts.completed,
        "failed": counts.failed,
        "recovery_required": counts.recovery_required,
        "cancelled": counts.cancelled,
        "total": counts.total,
    }


def _batch_job_payload(batch, job_id: str) -> dict:
    job = jobs.get(job_id)
    status = batch.job_statuses[job_id]
    original_filename = os.path.basename(getattr(job, "pdf_path", "")) if job else ""
    output_pdf = _download_pdf_path(job_id) if status == "completed" else None
    output_pdf_safe = bool(output_pdf and _is_runtime_output_path(output_pdf))
    output_pdf_exists = bool(output_pdf_safe and os.path.isfile(output_pdf))

    payload = {
        "job_id": job_id,
        "original_filename": original_filename or "Unknown PDF",
        "mode": getattr(job, "mode", "auto") if job else "auto",
        "status": status,
        "output_pdf_exists": output_pdf_exists,
        "output_pdf_safe": output_pdf_safe,
        "retry_of_job_id": getattr(job, "retry_of_job_id", None) if job else None,
        "attempt_number": getattr(job, "attempt_number", 1) if job else 1,
    }
    if job and isinstance(getattr(job, "page_count", None), int):
        payload["page_count"] = job.page_count
    error = getattr(job, "error", None) if job else None
    if error:
        payload["error"] = error
    if output_pdf_exists:
        payload["download_url"] = f"/api/download/{job_id}"
    actions = []
    if status == STATUS_QUEUED:
        actions = ["pause", "remove"]
        queued_job_ids = [candidate for candidate in batch.job_ids if batch.job_statuses[candidate] == STATUS_QUEUED]
        queue_index = queued_job_ids.index(job_id)
        if queue_index > 0:
            actions.append("move_up")
        if queue_index < len(queued_job_ids) - 1:
            actions.append("move_down")
    elif status == STATUS_PAUSED:
        actions = ["resume", "remove"]
    elif status in {STATUS_FAILED, STATUS_RECOVERY_REQUIRED}:
        actions = ["retry"]
    payload["actions"] = actions
    return payload


def _batch_payload(batch) -> dict:
    return {
        "batch_id": batch.batch_id,
        "status": batch.status,
        "counts": _batch_counts_payload(batch.counts),
        "created_at": batch.created_at,
        "started_at": batch.started_at,
        "completed_at": batch.completed_at,
        "jobs": [_batch_job_payload(batch, job_id) for job_id in batch.job_ids],
    }


def _store_batch_update(batch) -> None:
    with _batch_lock:
        batches[batch.batch_id] = batch


def _queue_manifest_from_state() -> QueueManifest:
    saved_batches = []
    for batch in batches.values():
        saved_jobs = []
        for job_id in batch.job_ids:
            job = jobs.get(job_id)
            if job is None:
                continue
            saved_jobs.append(QueueJobRecord(
                job_id=job_id,
                status=batch.job_statuses[job_id],
                attempt_number=getattr(job, "attempt_number", 1),
                pdf_path=job.pdf_path,
                page_images=tuple(job.page_images),
                page_count=job.page_count,
                mode=job.mode,
                style=job.style,
                device=job.device,
                retry_of_job_id=getattr(job, "retry_of_job_id", None),
                error=getattr(job, "error", None),
            ))
        if len(saved_jobs) != len(batch.job_ids):
            continue
        saved_batches.append(QueueBatchRecord(
            batch_id=batch.batch_id,
            job_ids=batch.job_ids,
            jobs=tuple(saved_jobs),
            created_at=batch.created_at,
            started_at=batch.started_at,
            completed_at=batch.completed_at,
        ))
    return QueueManifest(batches=tuple(saved_batches))


def _persist_queue_manifest() -> None:
    save_queue_manifest(_queue_manifest_from_state())


def _get_batch(batch_id: str):
    with _batch_lock:
        return batches.get(batch_id)


def _run_batch(batch_id: str, runner: SingleWorkerBatchRunner) -> None:
    batch = batches[batch_id]

    def process_job(job_id: str) -> bool:
        job = jobs.get(job_id)
        if not job:
            raise RuntimeError(f"Job not found: {job_id}")

        q = queue.Queue()
        job_queues[job_id] = q
        out_dir = os.path.join(Config.OUTPUT_FOLDER, job_id)
        os.makedirs(out_dir, exist_ok=True)
        try:
            return _run_colorization_job(job_id, job, q, out_dir, batch_id=batch_id)
        except Exception as exc:
            logger.exception("Batch job %s failed before completion", job_id)
            job.status = "error"
            job.current_step = getattr(job, "current_step", "") or "batch processing"
            job.error = str(exc)
            raise
        finally:
            job_queues.pop(job_id, None)

    try:
        result = runner.start(batch, process_job)
        _store_batch_update(result.batch)
    except Exception:
        logger.exception("Batch processing failed for batch %s", batch_id)
    finally:
        with _batch_lock:
            active_batch_runners.pop(batch_id, None)


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


def _run_colorization_job(
    job_id: str,
    job,
    event_queue: queue.Queue,
    out_dir: str,
    batch_id: str | None = None,
) -> bool:
    current_step = "startup"
    timing = JobTiming()
    timing_step = None
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
        timing_step = timing.start_step("model_load")
        event_queue.put({"status": "model", "step": _model_progress_message(job.mode, current_step)})
        model_manager.switch_device(job.device)
        colorizer = model_manager.get_colorizer(
            job.mode,
            callback=_model_progress_callback(job, event_queue, job.mode),
        )
        timing.end_step(timing_step)
        timing_step = None

        use_reference_mode = job.mode == "reference"
        use_auto_mode = job.mode == "auto"
        jpeg_options = [cv2.IMWRITE_JPEG_QUALITY, 85]
        color_transfer_strength = Config.COLOR_TRANSFER_STRENGTH

        ref_image = None
        if use_reference_mode and job.reference_image_path:
            current_step = "reference preprocessing"
            job.current_step = current_step
            ref_image = _read_image_or_raise(
                job.reference_image_path,
                current_step,
                "reference",
                cv2_module=cv2,
            )

        consistency = ColorConsistencyManager() if use_auto_mode else None
        colored_paths = []

        timing_step = timing.start_step("page_colorization")
        page_timing_started_at = time.monotonic()
        with torch.inference_mode():
            for i, img_path in enumerate(job.page_images):
                current_step = f"page {i + 1} image loading"
                job.current_step = current_step
                event_queue.put({
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
                if use_reference_mode:
                    result = colorizer.colorize(image, reference_image=ref_image)
                else:
                    result = colorizer.colorize(image)

                current_step = f"page {i + 1} post-processing"
                job.current_step = current_step
                result = post_processor.process(result, image)

                if use_auto_mode:
                    current_step = f"page {i + 1} color consistency"
                    job.current_step = current_step
                    if i == 0:
                        consistency.set_reference(result)
                    else:
                        result = consistency.apply(
                            result,
                            strength=color_transfer_strength,
                        )

                out_path = os.path.join(out_dir, f"colored_{i:04d}.jpg")
                cv2.imwrite(out_path, result, jpeg_options)
                colored_paths.append(out_path)
                job.colorized_images.append(out_path)

                job.progress = (i + 1) / job.page_count
                completed_pages = i + 1
                remaining_pages = max(job.page_count - completed_pages, 0)
                elapsed_seconds = max(time.monotonic() - page_timing_started_at, 0.0)
                average_page_seconds = elapsed_seconds / completed_pages
                job.eta_seconds = round(average_page_seconds * remaining_pages, 1)
                progress_event = {
                    "page": i,
                    "total": job.page_count,
                    "status": "done_page",
                    "step": current_step,
                }
                if job.eta_seconds is not None:
                    progress_event["eta_seconds"] = job.eta_seconds
                event_queue.put(progress_event)
        timing.end_step(timing_step)
        timing_step = None

        current_step = "PDF export"
        job.current_step = current_step
        timing_step = timing.start_step("pdf_export")
        output_pdf = os.path.join(out_dir, "colorized.pdf")
        reassemble_pdf(colored_paths, output_pdf, job.pdf_path)
        timing.end_step(timing_step)
        timing_step = None
        job.output_pdf = output_pdf
        timing_step = timing.start_step("history_record")
        job.timing_summary = timing.summary()
        _record_completed_job_history(job, output_pdf, batch_id=batch_id)
        timing.end_step(timing_step)
        timing_step = None
        job.timing_summary = timing.summary()
        job.status = "done"
        event_queue.put({"done": True, "download_url": f"/api/download/{job_id}"})
        return True
    except Exception as e:
        if timing_step is not None:
            timing.fail_step(timing_step)
        job.timing_summary = timing.summary()
        job.eta_seconds = None
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
        event_queue.put({
            "error": _step_error_message(e, current_step),
            "step": current_step,
            "done": True,
        })
        return False


def _probe_device_summary():
    """Return best-effort device info without touching model weights."""
    capabilities = detect_device_capabilities()
    resolution = resolve_compute_device(
        Config.ML_DEVICE,
        capabilities=capabilities,
        official_cpu_build=is_official_cpu_build(),
    )
    return bool(resolution["cuda_available"]), resolution["resolved_device"]


def _device_diagnostics_payload(manager=None) -> dict:
    capabilities = detect_device_capabilities()
    official_cpu_build = is_official_cpu_build()
    resolution = resolve_compute_device(
        Config.ML_DEVICE,
        capabilities=capabilities,
        official_cpu_build=official_cpu_build,
    )
    payload = {
        "current": resolution["resolved_device"],
        "cuda_available": bool(resolution["cuda_available"]),
        "cuda_preview_enabled": not official_cpu_build,
        "requested_device": resolution["requested_device"],
        "default_device": Config.ML_DEVICE,
        "resolved_device": resolution["resolved_device"],
        "resolution": resolution,
        "capabilities": capabilities,
    }

    if manager is not None:
        payload["loaded_model_device"] = manager.device_name
        colorizer = getattr(manager, "_colorizer", None)
        fallback_reason = (
            getattr(colorizer, "fallback_reason", None)
            or getattr(colorizer, "failure_reason", None)
        )
        if fallback_reason:
            payload["fallback_reason"] = fallback_reason

    return payload


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


def _path_status(path: str) -> dict:
    return {
        "path": path,
        "exists": os.path.exists(path),
        "is_dir": os.path.isdir(path),
    }


def _disk_free_status(path: str) -> dict:
    target = path
    while target and not os.path.exists(target):
        parent = os.path.dirname(target)
        if parent == target:
            break
        target = parent
    try:
        usage = shutil.disk_usage(target or os.getcwd())
    except OSError as exc:
        return {"available": False, "error": str(exc)}
    return {
        "available": True,
        "checked_path": target or os.getcwd(),
        "free_bytes": usage.free,
        "total_bytes": usage.total,
    }


def _diagnostics_payload() -> dict:
    device = _device_diagnostics_payload(_model_manager)
    return {
        "python": {
            "version": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "process": {
            "cwd": os.getcwd(),
        },
        "paths": {
            "app": _path_status(Config.BASE_DIR),
            "runtime": _path_status(Config.RUNTIME_DIR),
            "uploads": _path_status(Config.UPLOAD_FOLDER),
            "output": _path_status(Config.OUTPUT_FOLDER),
            "models": _path_status(os.path.dirname(Config.WEIGHTS_DIR)),
            "weights": _path_status(Config.WEIGHTS_DIR),
            "cache": _path_status(Config.CACHE_DIR),
            "logs": _path_status(Config.LOG_DIR),
            "config": _path_status(Config.CONFIG_DIR),
        },
        "disk": {
            "runtime": _disk_free_status(Config.RUNTIME_DIR),
        },
        "model_manager": {
            "initialized": _model_manager is not None,
        },
        "device": device,
    }


def _app_version() -> str:
    return os.environ.get("COLORCOMIC_VERSION", "0.7.1")


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
    restore_queue_manifest()

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

    @app.route("/api/batches", methods=["POST"])
    def create_batch_upload():
        from core.pdf_handler import extract_pages, get_page_count
        from models.schemas import JobState

        mode = request.form.get("mode", "auto")
        if mode != "auto":
            return jsonify({"error": "Batch uploads support Auto mode only"}), 400

        files = []
        if hasattr(request.files, "getlist"):
            files = request.files.getlist("files") or request.files.getlist("file")

        if not files:
            return jsonify({"error": "No files uploaded", "jobs": [], "errors": []}), 400

        batch_id = str(uuid.uuid4())[:12]
        batch_dir = os.path.join(Config.UPLOAD_FOLDER, batch_id)
        os.makedirs(batch_dir, exist_ok=True)

        style = request.form.get("style", "auto")
        device = request.form.get("device", "auto")
        accepted_jobs = []
        errors = []

        for index, uploaded_file in enumerate(files):
            filename = getattr(uploaded_file, "filename", "") or f"file-{index + 1}"
            if not filename.lower().endswith(".pdf"):
                errors.append({
                    "filename": filename,
                    "code": "not_pdf",
                    "message": "Only PDF files are accepted.",
                })
                continue

            job_id = str(uuid.uuid4())[:12]
            job_dir = os.path.join(batch_dir, job_id)
            os.makedirs(job_dir, exist_ok=True)

            safe_name = _safe_uploaded_pdf_name(filename, f"input-{index + 1}")
            pdf_path = os.path.join(job_dir, safe_name)

            try:
                uploaded_file.save(pdf_path)
                preflight = validate_colorize_preflight(
                    pdf_path,
                    job_id,
                    Config.OUTPUT_FOLDER,
                    mode="auto",
                )
                preflight = _with_runtime_health(preflight)
                if not preflight.ok:
                    for error in preflight.errors:
                        errors.append({
                            "filename": filename,
                            "code": error.code,
                            "message": error.message,
                            "step": error.step,
                        })
                    continue

                page_count = preflight.page_count
                if not isinstance(page_count, int):
                    page_count = get_page_count(pdf_path)
                pages_dir = os.path.join(job_dir, "pages")
                page_images = extract_pages(pdf_path, pages_dir, dpi=Config.PAGE_DPI)
            except Exception as exc:
                logger.exception("Batch upload failed for file %s", filename)
                errors.append({
                    "filename": filename,
                    "code": "upload_failed",
                    "message": f"Could not prepare this PDF: {exc}",
                })
                continue

            job = JobState(
                job_id=job_id,
                pdf_path=pdf_path,
                page_count=page_count,
                page_images=page_images,
                style=style,
                device=device,
                mode="auto",
                reference_image_path=None,
            )
            jobs[job_id] = job
            accepted_jobs.append({
                "job_id": job_id,
                "filename": filename,
                "page_count": page_count,
                "mode": "auto",
            })

        if not accepted_jobs:
            return jsonify({"batch_id": None, "jobs": [], "errors": errors}), 400

        batch = create_batch(batch_id, [job["job_id"] for job in accepted_jobs])
        batches[batch_id] = batch

        return jsonify({
            "batch_id": batch_id,
            "jobs": accepted_jobs,
            "errors": errors,
        })

    @app.route("/api/batches/<batch_id>")
    def batch_status(batch_id):
        batch = batches.get(batch_id)
        if not batch:
            return jsonify({"error": "Batch not found"}), 404
        return jsonify(_batch_payload(batch))

    @app.route("/api/batches/<batch_id>/start", methods=["POST"])
    def start_batch(batch_id):
        with _batch_lock:
            batch = batches.get(batch_id)
            if not batch:
                return jsonify({"error": "Batch not found"}), 404
            if batch_id in active_batch_runners or batch.status == STATUS_RUNNING:
                return jsonify({"error": "Batch is already running"}), 409
            if batch.status != STATUS_QUEUED:
                return jsonify({"error": f"Batch cannot be started from status: {batch.status}"}), 409
            if batch.counts.queued == 0:
                return jsonify({"error": "Batch has no queued jobs"}), 400

            runner = SingleWorkerBatchRunner(on_update=_store_batch_update, get_latest=_get_batch)
            active_batch_runners[batch_id] = runner

        try:
            threading.Thread(target=lambda: _run_batch(batch_id, runner), daemon=True).start()
        except BatchQueueError as exc:
            with _batch_lock:
                active_batch_runners.pop(batch_id, None)
            return jsonify({"error": str(exc)}), 409
        except Exception as exc:
            logger.exception("Failed to start batch %s", batch_id)
            with _batch_lock:
                active_batch_runners.pop(batch_id, None)
            return jsonify({"error": f"Could not start batch: {exc}"}), 500

        return jsonify({"ok": True, "batch_id": batch_id, "status": "started"})

    @app.route("/api/batches/<batch_id>/jobs/<job_id>/cancel", methods=["POST"])
    def cancel_batch_job(batch_id, job_id):
        with _batch_lock:
            batch = batches.get(batch_id)
            if not batch:
                return jsonify({"error": "Batch not found"}), 404
            if job_id not in batch.job_statuses:
                return jsonify({"error": "Job not found"}), 404

            status = batch.job_statuses[job_id]
            if status == STATUS_RUNNING:
                return jsonify({"error": "Job is already running"}), 409
            if status == STATUS_COMPLETED:
                return jsonify({"error": "Job is already completed"}), 409
            if status == STATUS_CANCELLED:
                return jsonify({"error": "Job is already cancelled"}), 409
            if status != STATUS_QUEUED:
                return jsonify({"error": f"Job cannot be cancelled from status: {status}"}), 409

            try:
                batch = transition_job(batch, job_id, STATUS_CANCELLED)
            except BatchQueueError as exc:
                return jsonify({"error": str(exc)}), 409
            batches[batch_id] = batch

        return jsonify({
            "ok": True,
            "batch_id": batch_id,
            "job_id": job_id,
            "status": STATUS_CANCELLED,
            "batch": _batch_payload(batch),
        })

    @app.route("/api/batches/<batch_id>/jobs/<job_id>/pause", methods=["POST"])
    def pause_batch_job(batch_id, job_id):
        with _batch_lock:
            batch = batches.get(batch_id)
            if not batch:
                return jsonify({"error": "Batch not found"}), 404
            if job_id not in batch.job_statuses:
                return jsonify({"error": "Job not found"}), 404
            if batch.job_statuses[job_id] != STATUS_QUEUED:
                return jsonify({"error": "Only queued jobs can be paused"}), 409
            batch = transition_job(batch, job_id, STATUS_PAUSED)
            batches[batch_id] = batch
            _persist_queue_manifest()
        return jsonify({"ok": True, "job_id": job_id, "status": STATUS_PAUSED, "batch": _batch_payload(batch)})

    @app.route("/api/batches/<batch_id>/jobs/<job_id>/resume", methods=["POST"])
    def resume_batch_job(batch_id, job_id):
        with _batch_lock:
            batch = batches.get(batch_id)
            if not batch:
                return jsonify({"error": "Batch not found"}), 404
            if job_id not in batch.job_statuses:
                return jsonify({"error": "Job not found"}), 404
            if batch.job_statuses[job_id] != STATUS_PAUSED:
                return jsonify({"error": "Only paused jobs can be resumed"}), 409
            batch = transition_job(batch, job_id, STATUS_QUEUED)
            batches[batch_id] = batch
            _persist_queue_manifest()
        return jsonify({"ok": True, "job_id": job_id, "status": STATUS_QUEUED, "batch": _batch_payload(batch)})

    @app.route("/api/batches/<batch_id>/jobs/<job_id>/retry", methods=["POST"])
    def retry_batch_job(batch_id, job_id):
        from models.schemas import JobState

        with _batch_lock:
            batch = batches.get(batch_id)
            if not batch:
                return jsonify({"error": "Batch not found"}), 404
            if job_id not in batch.job_statuses or job_id not in jobs:
                return jsonify({"error": "Job not found"}), 404
            if batch.job_statuses[job_id] not in {STATUS_FAILED, STATUS_RECOVERY_REQUIRED}:
                return jsonify({"error": "Only failed or recovery-required jobs can be retried"}), 409
            parent = jobs[job_id]
            input_error = _recovery_input_error(parent)
            if input_error:
                return jsonify({"error": input_error}), 409

            retry_job_id = str(uuid.uuid4())[:12]
            while retry_job_id in jobs:
                retry_job_id = str(uuid.uuid4())[:12]
            retry_job = JobState(
                job_id=retry_job_id,
                pdf_path=parent.pdf_path,
                page_count=parent.page_count,
                page_images=list(parent.page_images),
                style=parent.style,
                device=parent.device,
                mode=parent.mode,
                reference_image_path=parent.reference_image_path,
                retry_of_job_id=job_id,
                attempt_number=getattr(parent, "attempt_number", 1) + 1,
            )
            job_statuses = dict(batch.job_statuses)
            job_statuses[retry_job_id] = STATUS_QUEUED
            batch = BatchRecord(
                batch_id=batch.batch_id,
                job_ids=(*batch.job_ids, retry_job_id),
                job_statuses=job_statuses,
                status=derive_batch_status(job_statuses, started_at=batch.started_at),
                created_at=batch.created_at,
                started_at=batch.started_at,
                completed_at=None,
            )
            jobs[retry_job_id] = retry_job
            batches[batch_id] = batch
            _persist_queue_manifest()
        return jsonify({"ok": True, "job_id": retry_job_id, "status": STATUS_QUEUED, "batch": _batch_payload(batch)})

    @app.route("/api/batches/<batch_id>/jobs/<job_id>/remove", methods=["POST"])
    def remove_batch_job(batch_id, job_id):
        with _batch_lock:
            batch = batches.get(batch_id)
            if not batch:
                return jsonify({"error": "Batch not found"}), 404
            if job_id not in batch.job_statuses:
                return jsonify({"error": "Job not found"}), 404
            if batch.job_statuses[job_id] not in {STATUS_QUEUED, STATUS_PAUSED}:
                return jsonify({"error": "Job cannot be removed from its current status"}), 409
            batch = remove_pending_job(batch, job_id)
            jobs.pop(job_id, None)
            batch_removed = not batch.job_ids
            if batch_removed:
                batches.pop(batch_id, None)
            else:
                batches[batch_id] = batch
            _persist_queue_manifest()
        return jsonify({"ok": True, "job_id": job_id, "batch_removed": batch_removed, "batch": None if batch_removed else _batch_payload(batch)})

    def move_batch_job(batch_id, job_id, direction):
        with _batch_lock:
            batch = batches.get(batch_id)
            if not batch:
                return jsonify({"error": "Batch not found"}), 404
            if job_id not in batch.job_statuses:
                return jsonify({"error": "Job not found"}), 404
            if batch.job_statuses[job_id] != STATUS_QUEUED:
                return jsonify({"error": "Only queued jobs can be reordered"}), 409
            queued_job_ids = [candidate for candidate in batch.job_ids if batch.job_statuses[candidate] == STATUS_QUEUED]
            queue_index = queued_job_ids.index(job_id)
            target_index = queue_index + direction
            if target_index < 0:
                return jsonify({"error": "Queued job is already first"}), 409
            if target_index >= len(queued_job_ids):
                return jsonify({"error": "Queued job is already last"}), 409
            batch = reorder_queued_job(batch, job_id, queued_job_ids[target_index])
            batches[batch_id] = batch
            _persist_queue_manifest()
        return jsonify({"ok": True, "job_id": job_id, "batch": _batch_payload(batch)})

    @app.route("/api/batches/<batch_id>/jobs/<job_id>/move-up", methods=["POST"])
    def move_batch_job_up(batch_id, job_id):
        return move_batch_job(batch_id, job_id, -1)

    @app.route("/api/batches/<batch_id>/jobs/<job_id>/move-down", methods=["POST"])
    def move_batch_job_down(batch_id, job_id):
        return move_batch_job(batch_id, job_id, 1)

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
        with _batch_lock:
            job = jobs.get(job_id)
            if not job:
                return jsonify({"error": "Job not found"}), 404
            if job.status == "colorizing" and job_id in job_queues:
                return jsonify({"error": "Job is already running"}), 409

            job.status = "colorizing"
            job.progress = 0.0
            q = queue.Queue()
            job_queues[job_id] = q

        preflight = validate_colorize_preflight(
            job.pdf_path,
            job_id,
            Config.OUTPUT_FOLDER,
            mode=getattr(job, "mode", "auto"),
            reference_image_path=getattr(job, "reference_image_path", None),
        )
        preflight = _with_runtime_health(preflight)
        if not preflight.ok:
            current_step = preflight.errors[0].step if preflight.errors else "preflight"
            with _batch_lock:
                if job_queues.get(job_id) is q:
                    job.status = "error"
                    job.current_step = current_step
            q.put({
                "error": _preflight_error_message(preflight.errors),
                "step": current_step,
                "done": True,
            })
            return jsonify({"ok": True})

        out_dir = preflight.output_dir

        def _run():
            try:
                _run_colorization_job(job_id, job, q, out_dir)
            finally:
                with _batch_lock:
                    if job_queues.get(job_id) is q:
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
                        job_queues.pop(job_id, None)
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

    @app.route("/api/recent-jobs")
    def recent_jobs():
        entries = sorted(
            load_job_history(),
            key=lambda entry: entry.completed_at,
            reverse=True,
        )
        return jsonify({"jobs": [_recent_job_payload(entry) for entry in entries]})

    @app.route("/api/recent-jobs/<job_id>", methods=["DELETE"])
    def delete_recent_job(job_id):
        entries = load_job_history()
        remaining = remove_job_history_entry(job_id)
        return jsonify({
            "removed": len(remaining) != len(entries),
            "job_id": job_id,
        })

    @app.route("/api/preferences", methods=["GET", "POST"])
    def preferences():
        if request.method == "GET":
            return jsonify({"preferences": load_preferences()})

        payload = request.get_json(silent=True)
        updates, error = _validate_preferences_update(payload)
        if error:
            return jsonify({"error": error, "preferences": load_preferences()}), 400

        preferences_payload = load_preferences()
        preferences_payload.update(updates)
        return jsonify({"preferences": save_preferences(preferences_payload)})

    @app.route("/api/preferences/reset", methods=["POST"])
    def reset_preferences_api():
        return jsonify({"preferences": reset_preferences()})

    @app.route("/api/health")
    def health():
        return jsonify({"ok": True, "service": "ColorComic"})

    @app.route("/api/status")
    def model_status():
        return jsonify(_model_status_payload())

    @app.route("/api/diagnostics")
    def diagnostics():
        return jsonify(_diagnostics_payload())

    @app.route("/api/diagnostics/bundle")
    def diagnostics_bundle():
        bundle_path = create_diagnostics_bundle(
            _diagnostics_payload(),
            Config.LOG_DIR,
            app_version=_app_version(),
        )
        return send_file(
            bundle_path,
            as_attachment=True,
            download_name=os.path.basename(bundle_path),
            mimetype="application/zip",
        )

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
