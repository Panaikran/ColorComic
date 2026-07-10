"""Cheap per-page quality heuristics.

Returns a 0–100 score plus a list of issue tags so the UI can flag
pages that probably need a retry.

All metrics are means/fractions (resolution-invariant), so scoring runs
on a ≤1024px copy with a single LAB conversion — full-res evaluation
cost gigabytes per page on upscaled output for identical numbers.
"""

from dataclasses import dataclass

import cv2
import numpy as np


# Max edge for evaluation — metrics are statistical, so scale changes nothing
_EVAL_MAX_EDGE = 1024


@dataclass
class PageQuality:
    score: int           # 0..100
    issues: list[str]    # short tags
    chroma_mean: float   # average LAB chroma (sat proxy)
    chroma_std: float    # variance
    skin_safety: float   # 0..1, how plausible skin tones are
    bleed_score: float   # 0..1, lower is better (color leaking into ink)


def _skin_safety(image_bgr: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    """Fraction of skin-classified pixels that fall in plausible skin LAB.

    Detects a rough skin mask in YCrCb, then checks LAB chroma is in a
    sensible band (not green-tinted, not magenta).
    """
    ycrcb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2YCrCb)
    cr = ycrcb[:, :, 1]
    cb = ycrcb[:, :, 2]
    skin = (cr >= 135) & (cr <= 180) & (cb >= 85) & (cb <= 135)
    if skin.sum() < 200:
        return 1.0  # nothing to flag

    a_s = a[skin]
    b_s = b[skin]
    # Plausible skin lives in roughly +5..+25 a, +10..+30 b (warm tones)
    plausible = (a_s >= 0) & (a_s <= 32) & (b_s >= 0) & (b_s <= 40)
    return float(plausible.mean())


def evaluate(image_bgr: np.ndarray, original_gray: np.ndarray) -> PageQuality:
    """Score a colorized page against its original."""
    issues: list[str] = []

    # Downscale ONCE — every metric below is scale-invariant
    h, w = image_bgr.shape[:2]
    max_edge = max(h, w)
    if max_edge > _EVAL_MAX_EDGE:
        scale = _EVAL_MAX_EDGE / max_edge
        image_bgr = cv2.resize(image_bgr, (int(w * scale), int(h * scale)),
                               interpolation=cv2.INTER_AREA)

    if original_gray.ndim == 3:
        gray = cv2.cvtColor(original_gray, cv2.COLOR_BGR2GRAY)
    else:
        gray = original_gray
    if gray.shape != image_bgr.shape[:2]:
        gray = cv2.resize(gray, (image_bgr.shape[1], image_bgr.shape[0]),
                          interpolation=cv2.INTER_AREA)

    # ONE LAB conversion shared by all three metrics
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    a = lab[:, :, 1] - 128.0
    b = lab[:, :, 2] - 128.0
    chroma = cv2.magnitude(a, b)

    # Chroma stats on a "non-ink, non-paper" sampling mask
    sample = (gray > 35) & (gray < 235)
    sampled = chroma[sample]
    if sampled.size:
        chroma_mean = float(sampled.mean())
        chroma_std = float(sampled.std())
    else:
        chroma_mean = chroma_std = 0.0

    # Color bleed into ink lines — those should be colorless
    ink = gray <= 50
    if ink.sum() < 50:
        bleed = 0.0
    else:
        bleed = min(1.0, float(chroma[ink].mean()) / 30.0)

    skin = _skin_safety(image_bgr, a, b)

    # Monochrome wash: nearly all colored pixels share one hue — the page
    # was tinted, not colored.  A properly colored page has several hue
    # clusters (skin / hair / clothes / background).
    wash_share = 0.0
    colored = sample & (chroma > 10.0)
    if colored.sum() > max(500, 0.02 * sample.size):
        hue = np.degrees(np.arctan2(b[colored], a[colored])) % 360.0
        hist, _ = np.histogram(hue, bins=36, range=(0.0, 360.0))
        p = hist / max(1, hist.sum())
        ext = np.concatenate([p, p[:4]])
        # widest +/-20 deg window (4 adjacent 10-deg bins, circular)
        wash_share = float(max(ext[i:i + 4].sum() for i in range(36)))

    score = 100.0
    if chroma_mean < 6.0:
        issues.append("low_saturation")
        score -= 20
    if chroma_mean > 55.0:
        issues.append("oversaturated")
        score -= 10
    if chroma_std < 5.0:
        issues.append("flat_palette")
        score -= 10
    if skin < 0.55:
        issues.append("skin_off")
        score -= 18
    if bleed > 0.45:
        issues.append("color_bleed")
        score -= 15
    if wash_share > 0.78:
        issues.append("monochrome_wash")
        score -= 20

    score = int(max(0, min(100, round(score))))

    return PageQuality(
        score=score,
        issues=issues,
        chroma_mean=chroma_mean,
        chroma_std=chroma_std,
        skin_safety=skin,
        bleed_score=bleed,
    )
