"""Guided colorist — segment, identify, assign, hint.

Orchestrates the "digital colorist" pipeline for auto (mc-v2) mode:

1. segment the page into lineart-bounded regions (region_segmenter)
2. label each region with local CLIP zero-shot (region_classifier)
3. look colors up in the job's color script (color_director — static
   palette, optionally refined once per job by a text-only LLM)
4. emit sparse color hint points that feed mc-v2's native hint channel

The colorization model itself keeps doing the painting — hints only tell
it WHAT color each thing is, which is exactly the information it was
hallucinating (as a single wash) before.
"""

import threading

import numpy as np

from core.color_director import ColorDirector, hex_to_bgr
from core.region_classifier import RegionClassifier
from core.region_segmenter import segment_regions

# One CLIP classifier per process — jobs share it
_classifier_lock = threading.Lock()
_shared_classifier: RegionClassifier | None = None


def _get_classifier() -> RegionClassifier:
    global _shared_classifier
    with _classifier_lock:
        if _shared_classifier is None:
            _shared_classifier = RegionClassifier()
        return _shared_classifier

# A hint point: (x_norm, y_norm, (r, g, b))
HintPoint = tuple[float, float, tuple[int, int, int]]

# Region classes that map straight onto a palette key
_DIRECT_KEYS = {"skin", "hair", "metal", "wood", "sky", "foliage",
                "stone", "water", "fire", "background"}
_CLOTHING_KEYS = ("clothing_primary", "clothing_secondary", "clothing_accent")

# Below this softmax confidence a label is noise — better no hint than a
# wrong one the model will happily propagate.
_MIN_CONF = 0.25


class GuidedColorist:
    """Per-job color guide. Build once per job, call hints_for_page per page."""

    def __init__(self, config, use_llm: bool | None = None):
        self._cfg = config
        self._use_llm = use_llm  # None = follow Config.LLM_DIRECTOR
        self._classifier = _get_classifier()
        self._director = ColorDirector(config)
        self._script: dict | None = None

    @property
    def available(self) -> bool:
        return self._classifier.available

    @property
    def script(self) -> dict | None:
        return self._script

    def prepare(self, sample_pages_bgr: list[np.ndarray]) -> None:
        """Build the job's color script from a few sample pages.

        Segments + labels the samples, summarizes the counts as TEXT, and
        lets the director (static palette or text-LLM) pick the palette.
        """
        counts: dict[str, int] = {}
        if self._classifier.available:
            for page in sample_pages_bgr:
                seg = segment_regions(page)
                if not seg.regions:
                    continue
                labels = self._classifier.classify(
                    page, [r.bbox for r in seg.regions])
                if not labels:
                    continue
                for (label, conf) in labels:
                    if conf >= _MIN_CONF:
                        counts[label] = counts.get(label, 0) + 1

        summary = {
            "pages_sampled": len(sample_pages_bgr),
            "region_counts": counts,
            "content_hint": "black-and-white manga/manhwa chapter",
        }
        self._script = self._director.build_script(summary, use_llm=self._use_llm)

    def hints_for_page(self, image_bgr: np.ndarray) -> list[HintPoint]:
        """Segment + label one page and return its color hint points."""
        if not self._classifier.available:
            return []
        if self._script is None:
            self.prepare([image_bgr])

        h, w = image_bgr.shape[:2]
        gray = (image_bgr if image_bgr.ndim == 2
                else np.mean(image_bgr, axis=2).astype(np.uint8))
        seg = segment_regions(image_bgr)
        if not seg.regions:
            return []

        labels = self._classifier.classify(image_bgr, [r.bbox for r in seg.regions])
        if not labels:
            return []

        def _on_tone(px: int, py: int) -> bool:
            """A dot must sit on a mid-tone pixel — never on paper or ink."""
            v = int(gray[min(h - 1, max(0, py)), min(w - 1, max(0, px))])
            return 70 <= v < 238

        palette = self._script["palette"]
        points: list[HintPoint] = []
        clothing_rank = 0

        for region, (label, conf) in zip(seg.regions, labels):
            # Paper, bubbles and ink must stay neutral — never hint them
            if label == "bubble" or conf < _MIN_CONF:
                continue
            if region.mean_gray >= 238 or region.mean_gray < 70:
                continue

            if label == "clothing":
                key = _CLOTHING_KEYS[clothing_rank % len(_CLOTHING_KEYS)]
                clothing_rank += 1
            elif label in _DIRECT_KEYS:
                key = label
            else:
                continue

            hex_color = palette.get(key)
            if not hex_color:
                continue
            b, g, r = hex_to_bgr(hex_color)
            rgb = (r, g, b)

            px, py = region.interior_point
            if _on_tone(px, py):
                points.append((px / w, py / h, rgb))

            # Large regions need more than one dot to carry the color —
            # but only on toned pixels, never on white highlights inside
            # the region (those must stay free for the model/post to keep)
            if region.frac > 0.008:
                for (ex, ey) in seg.interior_points(region):
                    if _on_tone(ex, ey):
                        points.append((ex / w, ey / h, rgb))

        return points
