"""Preflight checks for runtime inputs and writable job output paths."""

from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
import tempfile
from typing import Callable


PageCountReader = Callable[[str], int]
ImageReader = Callable[[str], object]
DiskUsageReader = Callable[[str], object]

MIN_RUNTIME_FREE_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True)
class PreflightError:
    code: str
    message: str
    step: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "step": self.step,
        }


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    pdf_path: str
    output_dir: str | None
    page_count: int | None
    reference_image_path: str | None
    errors: tuple[PreflightError, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "pdf_path": self.pdf_path,
            "output_dir": self.output_dir,
            "page_count": self.page_count,
            "reference_image_path": self.reference_image_path,
            "errors": [error.as_dict() for error in self.errors],
        }


def _default_page_count_reader(pdf_path: str) -> int:
    from core.pdf_handler import get_page_count

    return get_page_count(pdf_path)


def _default_image_reader(image_path: str):
    import cv2

    return cv2.imread(image_path)


def _resolve_output_job_dir(output_folder: str, job_id: str) -> str:
    output_root = os.path.abspath(output_folder)
    output_dir = os.path.abspath(os.path.join(output_root, job_id))
    if os.path.normcase(os.path.commonpath([output_root, output_dir])) != os.path.normcase(output_root):
        raise ValueError("Output job directory must stay under the output folder")
    if os.path.normcase(output_dir) == os.path.normcase(output_root):
        raise ValueError("Output job directory must not be the output folder itself")
    return output_dir


def _check_output_dir(output_folder: str, job_id: str) -> tuple[str | None, list[PreflightError]]:
    errors: list[PreflightError] = []
    try:
        output_dir = _resolve_output_job_dir(output_folder, job_id)
    except (OSError, ValueError):
        return None, [
            PreflightError(
                code="output_path_invalid",
                message="ColorComic could not prepare the output folder. Restart the app and try again.",
                step="output preflight",
            )
        ]

    try:
        os.makedirs(output_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".preflight-", dir=output_dir, delete=True):
            pass
    except OSError:
        errors.append(
            PreflightError(
                code="output_not_writable",
                message=(
                    "ColorComic cannot write to the output folder. "
                    "Check folder permissions or free space, then try again."
                ),
                step="output preflight",
            )
        )

    return output_dir, errors


def _check_writable_dir(path: str, code: str, label: str) -> PreflightError | None:
    try:
        os.makedirs(path, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".preflight-", dir=path, delete=True):
            pass
    except OSError:
        return PreflightError(
            code=code,
            message=f"ColorComic cannot write to the {label}. Check folder permissions or free space, then try again.",
            step="runtime preflight",
        )
    return None


def validate_runtime_health(
    runtime_dir: str,
    uploads_dir: str,
    output_dir: str,
    logs_dir: str,
    config_dir: str,
    min_free_bytes: int = MIN_RUNTIME_FREE_BYTES,
    disk_usage_reader: DiskUsageReader = shutil.disk_usage,
) -> tuple[PreflightError, ...]:
    errors: list[PreflightError] = []
    for path, code, label in (
        (runtime_dir, "runtime_not_writable", "runtime folder"),
        (uploads_dir, "uploads_not_writable", "uploads folder"),
        (output_dir, "output_not_writable", "output folder"),
        (logs_dir, "logs_not_writable", "logs folder"),
        (config_dir, "config_not_writable", "configuration folder"),
    ):
        error = _check_writable_dir(path, code, label)
        if error:
            errors.append(error)

    try:
        free_bytes = disk_usage_reader(runtime_dir).free
    except (AttributeError, OSError):
        errors.append(
            PreflightError(
                code="runtime_disk_unavailable",
                message="ColorComic could not check available disk space. Restart the app and try again.",
                step="runtime preflight",
            )
        )
    else:
        if free_bytes < min_free_bytes:
            errors.append(
                PreflightError(
                    code="runtime_disk_low",
                    message="ColorComic needs more free disk space before processing. Free some space and try again.",
                    step="runtime preflight",
                )
            )
    return tuple(errors)


def _image_has_valid_dimensions(image) -> bool:
    shape = getattr(image, "shape", None)
    if not shape or len(shape) < 2:
        return False
    height, width = shape[:2]
    return height > 0 and width > 0


def _check_reference_image(
    reference_image_path: str | None,
    image_reader: ImageReader | None,
) -> list[PreflightError]:
    if not reference_image_path:
        return [
            PreflightError(
                code="reference_missing",
                message="Choose a reference image before starting Reference mode.",
                step="reference preflight",
            )
        ]

    if not os.path.exists(reference_image_path):
        return [
            PreflightError(
                code="reference_missing",
                message="Choose the reference image again. ColorComic could not find it.",
                step="reference preflight",
            )
        ]

    if not os.path.isfile(reference_image_path):
        return [
            PreflightError(
                code="reference_not_file",
                message="Choose an image file for Reference mode.",
                step="reference preflight",
            )
        ]

    try:
        with open(reference_image_path, "rb") as handle:
            handle.read(1)
    except OSError:
        return [
            PreflightError(
                code="reference_not_readable",
                message="Choose the reference image again. ColorComic could not read it.",
                step="reference preflight",
            )
        ]

    try:
        reader = image_reader or _default_image_reader
        image = reader(reference_image_path)
    except Exception:
        return [
            PreflightError(
                code="reference_unreadable",
                message="Choose a valid PNG or JPEG reference image.",
                step="reference preflight",
            )
        ]

    if image is None:
        return [
            PreflightError(
                code="reference_unreadable",
                message="Choose a valid PNG or JPEG reference image.",
                step="reference preflight",
            )
        ]

    if not _image_has_valid_dimensions(image):
        return [
            PreflightError(
                code="reference_invalid_dimensions",
                message="Choose a reference image with visible width and height.",
                step="reference preflight",
            )
        ]

    return []


def validate_colorize_preflight(
    pdf_path: str,
    job_id: str,
    output_folder: str,
    page_count_reader: PageCountReader | None = None,
    mode: str = "auto",
    reference_image_path: str | None = None,
    image_reader: ImageReader | None = None,
) -> PreflightResult:
    """Validate uploaded PDF and output directory before CPU-heavy processing."""
    errors: list[PreflightError] = []
    page_count: int | None = None

    if not os.path.exists(pdf_path):
        errors.append(
            PreflightError(
                code="pdf_missing",
                message="Choose the PDF again. ColorComic could not find the uploaded file.",
                step="PDF preflight",
            )
        )
    elif not os.path.isfile(pdf_path):
        errors.append(
            PreflightError(
                code="pdf_not_file",
                message="Choose a PDF file, not a folder.",
                step="PDF preflight",
            )
        )
    else:
        try:
            with open(pdf_path, "rb") as handle:
                handle.read(1)
        except OSError:
            errors.append(
                PreflightError(
                    code="pdf_not_readable",
                    message="Choose the PDF again. ColorComic could not read this file.",
                    step="PDF preflight",
                )
            )

        if not any(error.code == "pdf_not_readable" for error in errors):
            try:
                reader = page_count_reader or _default_page_count_reader
                page_count = reader(pdf_path)
                if page_count < 1:
                    errors.append(
                        PreflightError(
                            code="pdf_has_no_pages",
                            message="Choose a PDF with at least one page.",
                            step="PDF preflight",
                        )
                    )
            except Exception:
                errors.append(
                    PreflightError(
                        code="pdf_unreadable",
                        message="Choose a valid PDF. ColorComic could not open this file.",
                        step="PDF preflight",
                    )
                )

    output_dir, output_errors = _check_output_dir(output_folder, job_id)
    errors.extend(output_errors)
    if mode == "reference":
        errors.extend(_check_reference_image(reference_image_path, image_reader))

    return PreflightResult(
        ok=not errors,
        pdf_path=pdf_path,
        output_dir=output_dir,
        page_count=page_count,
        reference_image_path=reference_image_path,
        errors=tuple(errors),
    )
