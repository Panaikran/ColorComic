"""Server-side paint-bucket recolor.

Floods a region from a click point and re-tones its chrominance to a
user-picked color, preserving luminance/lineart.

Used by the touch-up editor: the browser sends ``{x, y, hex}`` for a
single page; we fill that segment in LAB and write the new image.
"""

import cv2
import numpy as np


def hex_to_lab(hex_color: str) -> tuple[float, float, float]:
    """Convert "#RRGGBB" to (L, a, b) floats in OpenCV LAB scale."""
    s = hex_color.lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    r = int(s[0:2], 16); g = int(s[2:4], 16); b = int(s[4:6], 16)
    px = np.array([[[b, g, r]]], dtype=np.uint8)
    lab = cv2.cvtColor(px, cv2.COLOR_BGR2LAB)[0, 0]
    return float(lab[0]), float(lab[1]), float(lab[2])


def flood_recolor(image_bgr: np.ndarray, x: int, y: int, hex_color: str,
                  tolerance: int = 18, preserve_luminance: bool = True,
                  feather: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """Flood-fill from (x, y) and recolor to *hex_color*.

    Returns ``(new_image_bgr, mask_uint8)``.  The image is modified in
    place (and returned); the blur/LAB work runs only on the filled
    region's bounding box, not the whole page.
    """
    h, w = image_bgr.shape[:2]
    if x < 0 or y < 0 or x >= w or y >= h:
        return image_bgr, np.zeros((h, w), dtype=np.uint8)

    # Mask must be 2 px larger on each axis per cv2.floodFill spec.
    # FLOODFILL_MASK_ONLY means the image itself is never written — no copy.
    mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
    flood_flags = 4 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE
    cv2.floodFill(
        image_bgr, mask, (int(x), int(y)), (0, 0, 0),
        loDiff=(tolerance, tolerance, tolerance),
        upDiff=(tolerance, tolerance, tolerance),
        flags=flood_flags,
    )
    region = mask[1:-1, 1:-1]
    if not region.any():
        return image_bgr, region

    # Work only on the filled region's bounding box (+ feather margin)
    bx, by, bw, bh = cv2.boundingRect(region)
    margin = feather * 2 + 2
    x1 = max(0, bx - margin)
    y1 = max(0, by - margin)
    x2 = min(w, bx + bw + margin)
    y2 = min(h, by + bh + margin)

    roi_mask = region[y1:y2, x1:x2]
    if feather > 0:
        soft = cv2.GaussianBlur(roi_mask.astype(np.float32),
                                (feather * 2 + 1, feather * 2 + 1), 0) / 255.0
    else:
        soft = (roi_mask > 0).astype(np.float32)
    np.clip(soft, 0.0, 1.0, out=soft)

    # Apply LAB chrominance change inside the ROI only
    L_target, a_target, b_target = hex_to_lab(hex_color)
    roi = image_bgr[y1:y2, x1:x2]
    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB).astype(np.float32)

    lab[:, :, 1] = lab[:, :, 1] * (1.0 - soft) + a_target * soft
    lab[:, :, 2] = lab[:, :, 2] * (1.0 - soft) + b_target * soft
    if not preserve_luminance:
        lab[:, :, 0] = lab[:, :, 0] * (1.0 - soft) + L_target * soft
    np.clip(lab, 0, 255, out=lab)
    image_bgr[y1:y2, x1:x2] = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR)
    return image_bgr, region
