"""Post-processing pipeline for colorized manga pages.

Pipeline (each step toggleable / preset-driven):
1. L-channel chroma-aware blend — line work stays sharp, saturated areas
   keep more of their colorized luminance.
2. Hard masks + soft neutral preservation — speech bubbles, lineart,
   gutters and near-white/near-black mid-tones forced/faded to neutral
   (fused into ONE chroma multiply).
3. Guided filter — smooth color bleeding at edges using original as guide.
4. Saturation boost (vibrance curve) + optional warm/red chroma shift.
5. Real-ESRGAN 4x upscale (optional) — run LAST so every other step works
   at native resolution instead of 16x the pixel count.

All chroma steps share a single grayscale copy of the original and a
single float32 LAB conversion of the colorized page; the LAB→BGR
conversion happens exactly once at the end.
"""

import cv2
import numpy as np

from core.masks import combined_neutral_mask
from core.presets import StylePreset, get_style


# Max edge length for guided filter processing.  Larger images are
# downscaled before filtering to avoid multi-second CPU stalls on
# high-DPI pages (e.g. 300 DPI -> ~2500x3500 px).
_GUIDED_FILTER_MAX_EDGE = 1024


class PostProcessor:
    """Applies post-processing to improve colorized output quality."""

    def __init__(self, *, l_channel: bool = True, guided_filter: bool = True,
                 upscale: bool = False, upscaler=None,
                 neutral_preservation: bool = True,
                 saturation_boost: float = 1.3,
                 guided_filter_radius: int = 2,
                 guided_filter_eps: float = 0.01,
                 hard_masks: bool = True,
                 skin_correction: bool = False,
                 style: StylePreset | None = None):
        self.l_channel = l_channel
        self.guided_filter = guided_filter
        self.upscale = upscale
        self._upscaler = upscaler
        self.neutral_preservation = neutral_preservation
        self.saturation_boost = saturation_boost
        self.guided_filter_radius = guided_filter_radius
        self.guided_filter_eps = guided_filter_eps
        self.hard_masks = hard_masks
        self.skin_correction = skin_correction
        self.style = style or get_style("neutral")

    def process(self, colorized: np.ndarray, original_gray: np.ndarray,
                style: StylePreset | None = None) -> np.ndarray:
        """Run the post-processing pipeline (see module docstring for order).

        Parameters
        ----------
        colorized : np.ndarray
            Colorized image in BGR uint8, same size as *original_gray*.
        original_gray : np.ndarray
            Original B&W page in BGR uint8 (may be single-channel or 3-channel grayscale).
        style : StylePreset, optional
            Override the configured style preset for this call.
        """
        st = style or self.style
        result = colorized

        # Shared precomputes: ONE gray + ONE float32 LAB for every step
        gray = self._to_gray(original_gray)
        gray = self._match_size(gray, result.shape[:2])
        gray_f = gray.astype(np.float32)
        lab = cv2.cvtColor(result, cv2.COLOR_BGR2LAB).astype(np.float32)

        # 1. Chroma-aware L blend
        if self.l_channel:
            self._chroma_aware_l(lab, gray_f, alpha=st.l_blend_alpha,
                                 gamma=st.l_gamma)

        # 2. Hard masks + soft neutral fade — both are multiplicative on the
        # a/b deviations, so combine them into a single multiply.
        keep = None
        if self.hard_masks:
            keep = combined_neutral_mask(
                gray,
                line_low=55,
                bubble_white=max(225, st.white_threshold),
                gutter_white=240,
                line_dilate=1,
                blur=3,
            )
        if self.neutral_preservation:
            soft = self._neutral_fade_mask(
                gray_f,
                white_threshold=st.white_threshold,
                black_threshold=st.black_threshold,
                transition=st.neutral_transition,
            )
            # Floor the SOFT fade only — bright surfaces keep some color;
            # bubbles/gutters/ink still go to zero via the hard mask above
            floor = float(np.clip(st.neutral_fade_floor, 0.0, 1.0))
            if floor > 0.0:
                soft = floor + (1.0 - floor) * soft
            keep = soft if keep is None else keep * soft
        if keep is not None:
            lab[:, :, 1] = 128.0 + (lab[:, :, 1] - 128.0) * keep
            lab[:, :, 2] = 128.0 + (lab[:, :, 2] - 128.0) * keep

        # 3. Guided filter (operates on the float a/b channels in place)
        if self.guided_filter:
            self._apply_guided_filter(
                lab, gray,
                radius=self.guided_filter_radius,
                eps=self.guided_filter_eps,
            )

        # 4. Cel flattening — pull each lineart-bounded region's chroma
        # toward its own mean, so the page reads as distinct flat fills
        # (the manhwa look) instead of one gradient wash.
        if st.cel_flatten > 0.0:
            self._cel_flatten(lab, gray, strength=st.cel_flatten)

        # 5. Saturation boost + style chroma shift
        if self.saturation_boost > 1.0 or st.chroma_warm_shift or st.chroma_red_shift:
            self._boost_saturation(
                lab,
                factor=self.saturation_boost,
                warm_shift=st.chroma_warm_shift,
                red_shift=st.chroma_red_shift,
            )

        # 6. Skin-tone correction — nudge too-red skin toward the plausible
        # 40-55 deg CIELAB hue band (the model skews skin red)
        if self.skin_correction:
            self._correct_skin_tones(lab)

        # Single LAB→BGR conversion for the whole pipeline
        np.clip(lab, 0, 255, out=lab)
        result = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR)

        # 7. Upscale LAST — chroma post-processing is low-frequency, so
        # running it at 4x-upscaled resolution multiplied every step's cost
        # and memory by ~16 for no visual gain.
        if self.upscale and self._upscaler is not None:
            result = self._upscaler.upscale(result)

        return result

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _to_gray(original: np.ndarray) -> np.ndarray:
        if original.ndim == 3 and original.shape[2] == 3:
            return cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
        if original.ndim == 3:
            return original[:, :, 0]
        return original

    @staticmethod
    def _match_size(img: np.ndarray, target_hw: tuple[int, int]) -> np.ndarray:
        h, w = target_hw
        if img.shape[:2] == (h, w):
            return img
        interp = cv2.INTER_AREA if img.shape[0] > h else cv2.INTER_CUBIC
        return cv2.resize(img, (w, h), interpolation=interp)

    # ── L-channel ───────────────────────────────────────────────────────────

    @staticmethod
    def _chroma_aware_l(lab: np.ndarray, gray_f: np.ndarray,
                        alpha: float = 0.1, gamma: float = 1.0) -> None:
        """Blend the colorized L toward the original L based on a line mask.

        - Inside line/edge pixels: use the original L (sharp linework).
        - Outside line pixels: blend ``alpha`` of the colorized L back in,
          so saturated regions don't get dimmed by the inker's luminance.
        - Optional ``gamma`` lifts/lowers the L globally.

        Mutates ``lab[:, :, 0]`` in place.
        """
        # Sobel-edge map of the original — high near linework
        sobelx = cv2.Sobel(gray_f, cv2.CV_32F, 1, 0, ksize=3)
        sobely = cv2.Sobel(gray_f, cv2.CV_32F, 0, 1, ksize=3)
        edge = cv2.magnitude(sobelx, sobely)
        edge = cv2.GaussianBlur(edge, (5, 5), 0)
        edge_max = float(edge.max()) or 1.0
        edge_norm = np.clip(edge * (1.0 / edge_max), 0.0, 1.0)
        # Also treat dark pixels themselves as line area
        ink = (255.0 - gray_f) * (0.6 / 255.0)
        line_w = np.clip(np.maximum(edge_norm, ink), 0.0, 1.0)

        L_color = lab[:, :, 0]
        L_orig = gray_f

        # Where line_w=1 → L_orig; where line_w=0 → blend
        L_blend = L_orig * (1.0 - alpha) + L_color * alpha
        L_out = L_orig * line_w + L_blend * (1.0 - line_w)

        if abs(gamma - 1.0) > 1e-3:
            L_out = (np.clip(L_out / 255.0, 0, 1) ** gamma) * 255.0

        lab[:, :, 0] = np.clip(L_out, 0, 255)

    # ── Soft neutral fade mask ─────────────────────────────────────────────

    @staticmethod
    def _neutral_fade_mask(gray_f: np.ndarray,
                           white_threshold: int = 220,
                           black_threshold: int = 30,
                           transition: int = 30) -> np.ndarray:
        """Float [0,1] keep-mask fading chroma near white and black."""
        t = float(max(transition, 1))
        white_mask = np.clip((float(white_threshold) - gray_f) / t, 0.0, 1.0)
        black_mask = np.clip((gray_f - float(black_threshold)) / t, 0.0, 1.0)
        return white_mask * black_mask

    # ── Saturation / chroma shift ──────────────────────────────────────────

    @staticmethod
    def _boost_saturation(lab: np.ndarray, factor: float = 1.5,
                          warm_shift: float = 0.0,
                          red_shift: float = 0.0) -> None:
        """Vibrance + optional global chroma shift (in place on float LAB).

        The boost peaks at MID chroma and tapers toward both ends: genuinely
        colored regions get richer while near-neutral pixels — where a
        model's global color cast lives — are left alone.  (The previous
        curve boosted near-neutrals the most, which amplified the
        one-color-wash problem.)
        """
        a_f = lab[:, :, 1] - 128.0
        b_f = lab[:, :, 2] - 128.0

        chroma = cv2.magnitude(a_f, b_f)
        max_chroma = 80.0
        t = np.clip(chroma * (1.0 / max_chroma), 0.0, 1.0)
        adaptive = 1.0 + (factor - 1.0) * (4.0 * t * (1.0 - t))

        lab[:, :, 1] = 128.0 + a_f * adaptive + red_shift
        lab[:, :, 2] = 128.0 + b_f * adaptive + warm_shift

    # ── Cel flattening ─────────────────────────────────────────────────────

    @staticmethod
    def _cel_flatten(lab: np.ndarray, gray: np.ndarray, strength: float = 0.7,
                     line_low: int = 70, min_region: int = 600) -> None:
        """Blend each lineart-bounded region's chroma toward the region mean.

        Segments the page into regions enclosed by ink lines (like a colorist
        flood-filling cels), then pulls every pixel's a/b toward its region's
        mean color.  Gradient washes inside a region collapse into one clean
        fill while different regions keep their own distinct colors.

        Mutates ``lab[:, :, 1:]`` in place.
        """
        strength = float(np.clip(strength, 0.0, 1.0))
        if strength <= 0.0:
            return

        # Non-ink pixels form the fillable regions; ink (label 0 areas and
        # tiny slivers) keeps its original chroma
        mask = (gray > line_low).astype(np.uint8)
        n, labels = cv2.connectedComponents(mask, connectivity=4)
        if n <= 1:
            return

        flat = labels.ravel()
        counts = np.bincount(flat, minlength=n).astype(np.float64)
        safe = np.maximum(counts, 1.0)
        mean_a = np.bincount(flat, weights=lab[:, :, 1].ravel(), minlength=n) / safe
        mean_b = np.bincount(flat, weights=lab[:, :, 2].ravel(), minlength=n) / safe

        keep = counts >= min_region
        keep[0] = False  # background label = the ink itself

        # Per-pixel target + applicability via LUT passes
        target_a = mean_a.astype(np.float32)[labels]
        target_b = mean_b.astype(np.float32)[labels]
        w = (keep.astype(np.float32) * strength)[labels]

        lab[:, :, 1] += (target_a - lab[:, :, 1]) * w
        lab[:, :, 2] += (target_b - lab[:, :, 2]) * w

    # ── Skin-tone correction ───────────────────────────────────────────────

    @staticmethod
    def _correct_skin_tones(lab: np.ndarray, target_hue_deg: float = 42.0,
                            strength: float = 0.55) -> None:
        """Rotate too-red skin-like chroma toward the plausible skin band.

        Real skin of all tones clusters around 40-55 deg CIELAB hue; the
        colorization model skews it red (< 35 deg).  Only pixels that look
        like skin (moderate chroma, warm hue, mid-to-high luminance) are
        touched, and the rotation is capped so saturated red clothing and
        deep shadows are unaffected.

        Mutates ``lab[:, :, 1:]`` in place.
        """
        L = lab[:, :, 0]
        a_f = lab[:, :, 1] - 128.0
        b_f = lab[:, :, 2] - 128.0
        chroma = cv2.magnitude(a_f, b_f)
        hue = np.degrees(np.arctan2(b_f, a_f))

        skin_like = (
            (chroma > 8.0) & (chroma < 45.0)      # skin is never neon
            & (hue > -8.0) & (hue < 34.0)          # the too-red side only
            & (L > 100.0) & (L < 238.0)            # mid/high luminance
        )
        if not skin_like.any():
            return

        rot = np.zeros_like(hue)
        rot[skin_like] = np.clip(
            (target_hue_deg - hue[skin_like]) * strength, -14.0, 14.0)
        rad = np.radians(rot)
        cos_r = np.cos(rad)
        sin_r = np.sin(rad)
        a_new = a_f * cos_r - b_f * sin_r
        b_new = a_f * sin_r + b_f * cos_r
        lab[:, :, 1] = 128.0 + a_new
        lab[:, :, 2] = 128.0 + b_new

    # ── Guided filter ──────────────────────────────────────────────────────

    @staticmethod
    def _apply_guided_filter(lab: np.ndarray, gray: np.ndarray,
                             radius: int = 2, eps: float = 0.01) -> None:
        """Guided-filter the a/b chroma channels using the original as guide.

        Mutates ``lab[:, :, 1:]`` in place; works on a downscaled copy for
        large pages.
        """
        full_h, full_w = lab.shape[:2]
        max_edge = max(full_h, full_w)
        need_downscale = max_edge > _GUIDED_FILTER_MAX_EDGE

        if need_downscale:
            scale = _GUIDED_FILTER_MAX_EDGE / max_edge
            small_w = int(full_w * scale)
            small_h = int(full_h * scale)
            a_f = cv2.resize(lab[:, :, 1], (small_w, small_h),
                             interpolation=cv2.INTER_AREA) * (1.0 / 255.0)
            b_f = cv2.resize(lab[:, :, 2], (small_w, small_h),
                             interpolation=cv2.INTER_AREA) * (1.0 / 255.0)
            guide_f = cv2.resize(gray, (small_w, small_h),
                                 interpolation=cv2.INTER_AREA).astype(np.float32) * (1.0 / 255.0)
        else:
            a_f = lab[:, :, 1] * (1.0 / 255.0)
            b_f = lab[:, :, 2] * (1.0 / 255.0)
            guide_f = gray.astype(np.float32) * (1.0 / 255.0)

        try:
            a_f = cv2.ximgproc.guidedFilter(guide_f, a_f, radius, eps)
            b_f = cv2.ximgproc.guidedFilter(guide_f, b_f, radius, eps)
        except AttributeError:
            # Fallback: bilateral on the chroma channel if ximgproc is missing
            a_f = cv2.bilateralFilter(a_f, 5, 0.05, 5)
            b_f = cv2.bilateralFilter(b_f, 5, 0.05, 5)

        if need_downscale:
            a_f = cv2.resize(a_f, (full_w, full_h), interpolation=cv2.INTER_CUBIC)
            b_f = cv2.resize(b_f, (full_w, full_h), interpolation=cv2.INTER_CUBIC)

        lab[:, :, 1] = a_f * 255.0
        lab[:, :, 2] = b_f * 255.0
