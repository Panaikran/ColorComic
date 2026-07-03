"""Preflight checks for runtime inputs and writable job output paths."""

from __future__ import annotations

from dataclasses import dataclass
import os
import tempfile
from typing import Callable


PageCountReader = Callable[[str], int]
ImageReader = Callable[[str], object]


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
    except (OSError, ValueError) as exc:
        return None, [
            PreflightError(
                code="output_path_invalid",
                message=str(exc),
                step="output preflight",
            )
        ]

    try:
        os.makedirs(output_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".preflight-", dir=output_dir, delete=True):
            pass
    except OSError as exc:
        errors.append(
            PreflightError(
                code="output_not_writable",
                message=f"Output directory is not writable: {exc}",
                step="output preflight",
            )
        )

    return output_dir, errors


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
                message="Reference mode requires a reference image",
                step="reference preflight",
            )
        ]

    if not os.path.exists(reference_image_path):
        return [
            PreflightError(
                code="reference_missing",
                message="Reference image does not exist",
                step="reference preflight",
            )
        ]

    if not os.path.isfile(reference_image_path):
        return [
            PreflightError(
                code="reference_not_file",
                message="Reference image path is not a file",
                step="reference preflight",
            )
        ]

    try:
        with open(reference_image_path, "rb") as handle:
            handle.read(1)
    except OSError as exc:
        return [
            PreflightError(
                code="reference_not_readable",
                message=f"Reference image is not readable: {exc}",
                step="reference preflight",
            )
        ]

    try:
        reader = image_reader or _default_image_reader
        image = reader(reference_image_path)
    except Exception as exc:
        return [
            PreflightError(
                code="reference_unreadable",
                message=f"Reference image could not be opened: {exc}",
                step="reference preflight",
            )
        ]

    if image is None:
        return [
            PreflightError(
                code="reference_unreadable",
                message="Reference image could not be decoded",
                step="reference preflight",
            )
        ]

    if not _image_has_valid_dimensions(image):
        return [
            PreflightError(
                code="reference_invalid_dimensions",
                message="Reference image has invalid dimensions",
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
                message="Uploaded PDF does not exist",
                step="PDF preflight",
            )
        )
    elif not os.path.isfile(pdf_path):
        errors.append(
            PreflightError(
                code="pdf_not_file",
                message="Uploaded PDF path is not a file",
                step="PDF preflight",
            )
        )
    else:
        try:
            with open(pdf_path, "rb") as handle:
                handle.read(1)
        except OSError as exc:
            errors.append(
                PreflightError(
                    code="pdf_not_readable",
                    message=f"Uploaded PDF is not readable: {exc}",
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
                            message="Uploaded PDF must contain at least one page",
                            step="PDF preflight",
                        )
                    )
            except Exception as exc:
                errors.append(
                    PreflightError(
                        code="pdf_unreadable",
                        message=f"Uploaded PDF could not be opened: {exc}",
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
