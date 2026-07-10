"""Mask builders for clean post-processing.

Provides:
- ``lineart_mask``     — pixels that are ink lines (fully desaturated).
- ``bubble_mask``      — speech-bubble interiors (fully desaturated).
- ``gutter_mask``      — page-margin / inter-panel gutters (fully desaturated).
- ``screentone_mask``  — halftone dot-pattern regions (low-pass before color).
- ``combined_neutral`` — float [0,1] mask: 1 = keep colorized chroma, 0 = neutral.
"""

import cv2
import numpy as np


def _to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3 and image.shape[2] == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image


def lineart_mask(gray: np.ndarray, low: int = 60, dilate: int = 0) -> np.ndarray:
    """Boolean mask of ink-line pixels (very dark pixels).

    Optional dilate widens the line a hair so anti-aliased halos along
    edges are also forced to neutral.
    """
    g = _to_gray(gray)
    mask = g <= low
    if dilate > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (dilate, dilate))
        mask = cv2.dilate(mask.astype(np.uint8), kernel).astype(bool)
    return mask


def bubble_mask(gray: np.ndarray, white_thr: int = 235,
                 min_area_ratio: float = 0.0008) -> np.ndarray:
    """Boolean mask of speech-bubble interiors (large near-white blobs)."""
    g = _to_gray(gray)
    h, w = g.shape[:2]
    page_area = h * w
    min_area = max(64, int(page_area * min_area_ratio))

    _, white = cv2.threshold(g, white_thr, 255, cv2.THRESH_BINARY)
    # Close small gaps in bubble outlines that would otherwise leak ink
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    white = cv2.morphologyEx(white, cv2.MORPH_OPEN, kernel)

    # Connected components — keep blobs that are bounded (not page background)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(white, connectivity=8)
    if n <= 1:
        return np.zeros_like(g, dtype=bool)
    x = stats[:, cv2.CC_STAT_LEFT]
    y = stats[:, cv2.CC_STAT_TOP]
    ww = stats[:, cv2.CC_STAT_WIDTH]
    hh = stats[:, cv2.CC_STAT_HEIGHT]
    area = stats[:, cv2.CC_STAT_AREA]
    keep = (
        (area >= min_area)
        # Skip blobs that fill most of the page
        & (area <= page_area * 0.4)
        # Skip blobs that touch the image border (those are page background)
        & (x > 0) & (y > 0) & (x + ww < w) & (y + hh < h)
    )
    keep[0] = False  # background label
    # Single vectorized LUT pass instead of one full-image scan per blob
    return keep[labels]


def gutter_mask(gray: np.ndarray, white_thr: int = 240,
                edge_band: float = 0.04) -> np.ndarray:
    """Boolean mask of likely page-edge gutters (white border strip)."""
    g = _to_gray(gray)
    h, w = g.shape[:2]
    band_h = max(8, int(h * edge_band))
    band_w = max(8, int(w * edge_band))

    out = np.zeros_like(g, dtype=bool)
    # Top
    out[:band_h] |= g[:band_h] >= white_thr
    # Bottom
    out[-band_h:] |= g[-band_h:] >= white_thr
    # Left
    out[:, :band_w] |= g[:, :band_w] >= white_thr
    # Right
    out[:, -band_w:] |= g[:, -band_w:] >= white_thr
    return out


def screentone_mask(gray: np.ndarray, tile: int = 32,
                    var_low: int = 200, var_high: int = 1800) -> np.ndarray:
    """Boolean mask of halftone screentone regions (mid-frequency texture).

    Halftones present as regular high-frequency variance in mid-grey.
    We block-pool variance and pick blocks whose variance falls in a
    "textured but not lineart" band.
    """
    g = _to_gray(gray).astype(np.float32)
    h, w = g.shape[:2]

    # Box-mean and box-var via integral images
    mean = cv2.boxFilter(g, ddepth=-1, ksize=(tile, tile), normalize=True)
    sqmean = cv2.boxFilter(g * g, ddepth=-1, ksize=(tile, tile), normalize=True)
    var = sqmean - mean * mean
    np.clip(var, 0, None, out=var)

    is_textured = (var >= var_low) & (var <= var_high)
    is_midtone = (mean >= 80) & (mean <= 210)
    return is_textured & is_midtone


def softmask_from_bool(mask: np.ndarray, blur: int = 5) -> np.ndarray:
    """Convert a boolean mask to a smooth float [0,1] mask."""
    f = mask.astype(np.float32)
    if blur > 0:
        f = cv2.GaussianBlur(f, (blur * 2 + 1, blur * 2 + 1), 0)
    np.clip(f, 0.0, 1.0, out=f)
    return f


def combined_neutral_mask(
    gray: np.ndarray,
    *,
    line_low: int = 60,
    bubble_white: int = 235,
    gutter_white: int = 240,
    line_dilate: int = 1,
    blur: int = 5,
) -> np.ndarray:
    """Float mask in [0,1] — 1 keep colorized chroma, 0 force neutral.

    Combines lineart, speech bubbles, and gutters into one preserve-mask.
    """
    g = _to_gray(gray)

    line = lineart_mask(g, low=line_low, dilate=line_dilate)
    bubble = bubble_mask(g, white_thr=bubble_white)
    gutter = gutter_mask(g, white_thr=gutter_white)

    # Things to force neutral (ink, bubble interiors, page gutters)
    neutralize = line | bubble | gutter
    keep = (~neutralize).astype(np.float32)

    # Smooth so the mask transition isn't a hard edge
    if blur > 0:
        keep = cv2.GaussianBlur(keep, (blur * 2 + 1, blur * 2 + 1), 0)
    np.clip(keep, 0.0, 1.0, out=keep)
    return keep


def deherron_screentones(gray: np.ndarray, strength: float = 0.6) -> np.ndarray:
    """Soften screentone regions so the colorizer doesn't see fake texture.

    Returns a uint8 grayscale image with halftones blurred but linework
    sharp.  ``strength`` 0 = passthrough, 1 = fully blurred screentones.
    """
    g = _to_gray(gray).astype(np.uint8)
    if strength <= 0.0:
        return g

    mask = screentone_mask(g)
    soft = softmask_from_bool(mask, blur=3)

    blurred = cv2.GaussianBlur(g, (5, 5), 0)
    out = g.astype(np.float32) * (1.0 - soft * strength) + \
          blurred.astype(np.float32) * (soft * strength)
    return np.clip(out, 0, 255).astype(np.uint8)
