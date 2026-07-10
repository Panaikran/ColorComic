"""Output writers — JPEG, PNG, and (optional) CMYK with embedded ICC.

The CMYK path requires Pillow with the ``littlecms`` C bindings (bundled
with most Pillow wheels).  If anything fails, we silently fall back to
sRGB output.
"""

import os
from typing import Optional

import cv2
import numpy as np


# ── sRGB ICC profile (lightweight, optional) ────────────────────────────────


_SRGB_ICC: Optional[bytes] = None


def _load_srgb_icc() -> Optional[bytes]:
    global _SRGB_ICC
    if _SRGB_ICC is not None:
        return _SRGB_ICC
    try:
        from PIL import ImageCms
        prof = ImageCms.createProfile("sRGB")
        _SRGB_ICC = ImageCms.ImageCmsProfile(prof).tobytes()
        return _SRGB_ICC
    except Exception:
        return None


# ── PNG / JPEG writers ──────────────────────────────────────────────────────


def write_image(path: str, image_bgr: np.ndarray, *,
                fmt: str = "jpg", jpeg_quality: int = 92,
                embed_icc: bool = True) -> str:
    """Write *image_bgr* to *path*.

    Returns the actual path written (extension may have been corrected).
    """
    fmt = fmt.lower()
    base, ext = os.path.splitext(path)
    target_ext = ".png" if fmt == "png" else ".jpg"
    if ext.lower() != target_ext:
        path = base + target_ext

    if fmt == "png":
        # Try Pillow with ICC first, fall back to OpenCV
        if embed_icc and _write_png_with_icc(path, image_bgr):
            return path
        cv2.imwrite(path, image_bgr, [cv2.IMWRITE_PNG_COMPRESSION, 5])
        return path

    # JPEG
    if embed_icc and _write_jpeg_with_icc(path, image_bgr, jpeg_quality):
        return path
    cv2.imwrite(path, image_bgr, [cv2.IMWRITE_JPEG_QUALITY, int(jpeg_quality)])
    return path


def _write_png_with_icc(path: str, image_bgr: np.ndarray) -> bool:
    """Pillow-based PNG writer that embeds an sRGB ICC."""
    icc = _load_srgb_icc()
    if icc is None:
        return False
    try:
        from PIL import Image
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        Image.fromarray(rgb).save(path, format="PNG", icc_profile=icc, optimize=False)
        return True
    except Exception:
        return False


def _write_jpeg_with_icc(path: str, image_bgr: np.ndarray, quality: int) -> bool:
    """Pillow-based JPEG writer that embeds an sRGB ICC."""
    icc = _load_srgb_icc()
    if icc is None:
        return False
    try:
        from PIL import Image
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        Image.fromarray(rgb).save(path, format="JPEG", quality=int(quality),
                                  icc_profile=icc, subsampling=0, optimize=True)
        return True
    except Exception:
        return False


def write_preview(path: str, image_bgr: np.ndarray, *,
                  max_width: int = 720, jpeg_quality: int = 82) -> str:
    """Write a downscaled JPEG preview (for browser thumbnails/streams).

    Serving multi-MB full-res pages to the browser for every progress
    update / page flip dwarfs every other frontend cost.
    """
    h, w = image_bgr.shape[:2]
    if w > max_width:
        scale = max_width / w
        image_bgr = cv2.resize(image_bgr, (max_width, max(1, int(h * scale))),
                               interpolation=cv2.INTER_AREA)
    cv2.imwrite(path, image_bgr, [cv2.IMWRITE_JPEG_QUALITY, int(jpeg_quality)])
    return path


# ── CMYK export ─────────────────────────────────────────────────────────────


def write_cmyk_tiff(path: str, image_bgr: np.ndarray) -> Optional[str]:
    """Convert sRGB → CMYK and write a print-ready TIFF.

    Returns the path on success, or ``None`` if Pillow / LCMS is missing.
    """
    try:
        from PIL import Image, ImageCms
    except Exception:
        return None
    try:
        srgb = ImageCms.createProfile("sRGB")
        # USWebCoatedSWOP-equivalent generic CMYK
        cmyk = ImageCms.createProfile("USWebCoatedSWOP")
    except Exception:
        # createProfile may not support CMYK names on all builds — fall back
        return None

    try:
        rgb_pil = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
        transform = ImageCms.buildTransformFromOpenProfiles(
            srgb, cmyk, "RGB", "CMYK", renderingIntent=ImageCms.INTENT_PERCEPTUAL,
        )
        cmyk_img = ImageCms.applyTransform(rgb_pil, transform)
        base, _ = os.path.splitext(path)
        tiff_path = base + ".tiff"
        cmyk_img.save(tiff_path, format="TIFF", compression="tiff_lzw")
        return tiff_path
    except Exception:
        return None
