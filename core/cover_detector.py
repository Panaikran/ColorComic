"""Pick the best 'palette anchor' page from a B&W comic.

Most B&W comics have one or two colored pages — the cover or a splash
spread.  Using that page as the reference for cross-page color
consistency gives much better results than blindly using page 0
(which is often a logo / title card).
"""

import cv2
import numpy as np


def chroma_score(image_path: str) -> float:
    """Average LAB chroma of an image.  Higher = more colorful.

    Decodes at 1/8 resolution — mean chroma is statistically identical on
    a thumbnail, and full-size 300-DPI pages cost seconds each to decode.
    """
    img = cv2.imread(image_path, cv2.IMREAD_REDUCED_COLOR_8)
    if img is None:
        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        return 0.0
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    a = lab[:, :, 1] - 128.0
    b = lab[:, :, 2] - 128.0
    return float(np.sqrt(a * a + b * b).mean())


def detect_anchor_page(page_paths: list[str], min_chroma: float = 4.0) -> int:
    """Return the index of the best palette-anchor page among the originals.

    If no page has meaningful chroma (a pure B&W book), returns 0.
    Otherwise returns the most colorful page in the first 10 pages
    (covers/splashes live near the front).
    """
    if not page_paths:
        return 0

    head = page_paths[: min(len(page_paths), 10)]
    best_idx = 0
    best_score = -1.0
    for i, p in enumerate(head):
        s = chroma_score(p)
        if s > best_score:
            best_score = s
            best_idx = i

    if best_score < min_chroma:
        return 0
    return best_idx
