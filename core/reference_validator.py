"""Validate user-supplied reference images before a long job runs.

Returns a structured verdict the UI can show:
- ``rating`` in {"good", "ok", "poor"}
- ``messages`` — human-readable findings
- ``suggestions`` — what the user could do to improve
"""

from dataclasses import dataclass, asdict

import cv2
import numpy as np


@dataclass
class ReferenceVerdict:
    rating: str
    messages: list[str]
    suggestions: list[str]
    width: int
    height: int
    saturation: float
    chroma_variance: float

    def to_json(self) -> dict:
        return asdict(self)


_MIN_EDGE = 512
_GOOD_EDGE = 1024
_MIN_SAT = 8.0
_GOOD_SAT = 18.0


def validate(image_bgr: np.ndarray) -> ReferenceVerdict:
    """Score a reference image for suitability."""
    h, w = image_bgr.shape[:2]
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    a = lab[:, :, 1] - 128.0
    b = lab[:, :, 2] - 128.0
    chroma = np.sqrt(a * a + b * b)
    sat_mean = float(chroma.mean())
    sat_var = float(chroma.std())

    messages: list[str] = []
    suggestions: list[str] = []
    rating_score = 100

    # Resolution check
    short_edge = min(h, w)
    if short_edge < _MIN_EDGE:
        messages.append(f"Low resolution ({w}×{h}) — expect detail loss.")
        suggestions.append(f"Use a reference at least {_MIN_EDGE}px on the short edge.")
        rating_score -= 35
    elif short_edge < _GOOD_EDGE:
        messages.append(f"Resolution is OK ({w}×{h}) but {_GOOD_EDGE}px+ is best.")
        rating_score -= 10
    else:
        messages.append(f"Resolution is good ({w}×{h}).")

    # Saturation check
    if sat_mean < _MIN_SAT:
        messages.append("Reference is nearly grayscale — too few colors to transfer.")
        suggestions.append("Pick a reference page where skin, hair, clothes and "
                           "background each have their own distinct color.")
        rating_score -= 40
    elif sat_mean < _GOOD_SAT:
        messages.append("Reference has moderate saturation; results will be subdued.")
        rating_score -= 10
    else:
        messages.append("Reference has rich color information.")

    # Variance — flat palette warning (a one-hue reference produces a
    # one-hue result: the "single wash" look)
    if sat_var < 6.0:
        messages.append("Palette is very flat (one dominant hue) — output will "
                        "look like a single-color wash.")
        suggestions.append("Use a reference with several distinct colors "
                           "(characters AND background), like a finished manhwa page.")
        rating_score -= 15

    if rating_score >= 80:
        rating = "good"
    elif rating_score >= 55:
        rating = "ok"
    else:
        rating = "poor"

    return ReferenceVerdict(
        rating=rating,
        messages=messages,
        suggestions=suggestions,
        width=w,
        height=h,
        saturation=sat_mean,
        chroma_variance=sat_var,
    )
