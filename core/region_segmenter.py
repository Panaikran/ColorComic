"""Lineart-bounded region segmentation (trapped-ball style).

Splits a manga page into the regions a colorist would flood-fill: areas
enclosed by ink lines.  Small gaps in the lineart are sealed by dilating
the ink mask before labeling (the poor man's trapped-ball), so fills
don't leak between a character and the background through a broken line.

The output feeds the guided-coloring pipeline: each region gets a CLIP
label and a palette color, which become sparse color hints for mc-v2.
"""

from dataclasses import dataclass

import cv2
import numpy as np


# Segmentation runs on a downscaled copy — region geometry is coarse by
# nature and 300-DPI pages would waste seconds per page.
_SEG_MAX_EDGE = 1400


@dataclass
class Region:
    """One fillable region, coordinates in FULL-RES pixels."""

    label_id: int
    area: int
    bbox: tuple[int, int, int, int]       # x, y, w, h
    interior_point: tuple[int, int]        # deepest point inside the region
    mean_gray: float                       # 0-255 tone of the region
    frac: float                            # area / page area


class Segmentation:
    """Region list plus the (downscaled) label map for interior sampling."""

    def __init__(self, regions: list[Region], labels: np.ndarray, scale: float):
        self.regions = regions
        self.labels = labels    # int32 label map at working scale
        self.scale = scale      # working px = full-res px * scale

    def interior_points(self, region: Region, spacing: int = 110,
                        max_points: int = 12) -> list[tuple[int, int]]:
        """Extra well-inside points for large regions (full-res coords).

        A single hint dot doesn't propagate across a big background —
        sprinkle a sparse grid of dots that stay clear of the borders.
        """
        m = (self.labels == region.label_id).astype(np.uint8)
        dist = cv2.distanceTransform(m, cv2.DIST_L2, 3)
        step = max(24, int(spacing * self.scale))
        pts: list[tuple[int, int]] = []
        h, w = dist.shape
        for yy in range(step // 2, h, step):
            for xx in range(step // 2, w, step):
                if dist[yy, xx] > 6:
                    pts.append((int(xx / self.scale), int(yy / self.scale)))
                    if len(pts) >= max_points:
                        return pts
        return pts


def segment_regions(gray: np.ndarray, *, line_low: int = 100, gap_close: int = 4,
                    min_area_frac: float = 0.0008,
                    max_regions: int = 28) -> Segmentation:
    """Segment a grayscale page into lineart-bounded regions.

    Parameters
    ----------
    gray : np.ndarray
        Grayscale (or BGR) page, uint8.
    line_low : int
        Pixels darker than this count as ink (region boundaries).
    gap_close : int
        Ink dilation radius in working pixels — seals lineart gaps up to
        ~2x this size so regions don't leak into each other.
    min_area_frac : float
        Regions smaller than this fraction of the page are ignored.
    max_regions : int
        Keep at most this many regions (largest first).
    """
    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]

    scale = 1.0
    g = gray
    if max(h, w) > _SEG_MAX_EDGE:
        scale = _SEG_MAX_EDGE / max(h, w)
        g = cv2.resize(gray, (int(w * scale), int(h * scale)),
                       interpolation=cv2.INTER_AREA)
    gh, gw = g.shape[:2]

    ink = (g < line_low).astype(np.uint8)
    if gap_close > 0:
        k = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (2 * gap_close + 1, 2 * gap_close + 1))
        ink = cv2.dilate(ink, k)

    fillable = (ink == 0).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(fillable, connectivity=4)

    page_area = gh * gw
    min_area = max(64, int(page_area * min_area_frac))
    inv = 1.0 / scale

    regions: list[Region] = []
    order = np.argsort(-stats[1:, cv2.CC_STAT_AREA]) + 1  # largest first
    for i in order:
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < min_area or len(regions) >= max_regions:
            break
        x, y, ww, hh = (int(stats[i, cv2.CC_STAT_LEFT]),
                        int(stats[i, cv2.CC_STAT_TOP]),
                        int(stats[i, cv2.CC_STAT_WIDTH]),
                        int(stats[i, cv2.CC_STAT_HEIGHT]))
        crop_mask = (labels[y:y + hh, x:x + ww] == i).astype(np.uint8)
        dist = cv2.distanceTransform(crop_mask, cv2.DIST_L2, 3)
        iy, ix = np.unravel_index(int(np.argmax(dist)), dist.shape)
        mean_gray = float(g[y:y + hh, x:x + ww][crop_mask.astype(bool)].mean())

        regions.append(Region(
            label_id=i,
            area=int(area * inv * inv),
            bbox=(int(x * inv), int(y * inv), int(ww * inv), int(hh * inv)),
            interior_point=(int((x + ix) * inv), int((y + iy) * inv)),
            mean_gray=mean_gray,
            frac=area / page_area,
        ))

    return Segmentation(regions, labels, scale)
