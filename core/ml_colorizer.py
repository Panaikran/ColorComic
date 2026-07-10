"""ML-based manga/comic colorization using manga-colorization-v2.

Adds:
- Tiled colorization at native page resolution (preserves fine detail).
- Per-panel colorization (uses panel_detector if requested).
- Screentone pre-cleaning before the model sees the page.
- Graceful OOM fallback: shrink first, retry, then drop to CPU.
"""

import gc
import math
import sys
import os
import threading

import cv2
import numpy as np
import torch

# Make vendor package importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vendor.manga_colorization_v2.colorizator import MangaColorizator
from core.masks import deherron_screentones
from core.panel_detector import detect_panels, extract_panel_image


def build_hint_arrays(h: int, w: int, size: int,
                      hint_points) -> tuple[np.ndarray, np.ndarray]:
    """Rasterize normalized hint points into mc-v2's hint + mask planes.

    Replicates ``resize_pad``'s geometry (resize then pad to /32) so the
    hint image lines up pixel-for-pixel with the model input.  Points are
    (x_norm, y_norm, (r, g, b)).
    """
    if h < w:  # landscape — resize_pad fixes height at size*1.5, pads width
        ratio = h / (size * 1.5)
        rh = int(size * 1.5)
        rw = int(np.ceil(w / ratio))
        ph, pw = rh, rw + ((-rw) % 32)
    else:      # portrait — fixes width at size, pads height
        ratio = w / size
        rw = size
        rh = int(np.ceil(h / ratio))
        ph, pw = rh + ((-rh) % 32), rw

    # Background MUST be mid-gray: update_hint normalizes with
    # (x/255 - 0.5) / 0.5, and the model's trained "no hint here" value is
    # 0 in that space (= 128 raw). A zero background normalizes to -1 —
    # a page-wide black hint — which collapses the output to grayscale.
    hint = np.full((ph, pw, 3), 128, dtype=np.uint8)
    mask = np.zeros((ph, pw), dtype=np.uint8)
    # 4px dots at model resolution — 2px was too subtle to steer the model
    radius = 4
    for (xn, yn, (r, g, b)) in hint_points:
        px = min(rw - 1, max(0, int(xn * rw)))
        py = min(rh - 1, max(0, int(yn * rh)))
        cv2.circle(hint, (px, py), radius, (int(r), int(g), int(b)), -1)
        cv2.circle(mask, (px, py), radius, 255, -1)
    return hint, mask


class MangaColorizer:
    """Wrapper around manga-colorization-v2 with tiled / per-panel paths."""

    def __init__(self, device: str = "auto",
                 generator_path: str = "",
                 extractor_path: str = "",
                 denoiser_weights_dir: str = ""):
        self._lock = threading.Lock()
        self._device = self._resolve_device(device)
        self._generator_path = generator_path
        self._extractor_path = extractor_path
        self._denoiser_weights_dir = denoiser_weights_dir
        self._model = MangaColorizator(
            device=self._device,
            generator_path=generator_path,
            extractor_path=extractor_path,
            denoiser_weights_dir=denoiser_weights_dir,
        )
        self.device_name = str(self._device)
        self.cuda_available = torch.cuda.is_available()

    @staticmethod
    def _resolve_device(device: str):
        if device == "auto":
            if torch.cuda.is_available():
                return torch.device("cuda")
            return torch.device("cpu")
        return torch.device(device)

    def to_device(self, device: str) -> None:
        """Move the loaded model between devices without reloading weights."""
        target = self._resolve_device(device)
        if str(target) == self.device_name:
            return
        with self._lock:
            self._model.colorizer.to(target)
            self._model.denoiser.to(target)
            self._model.device = target
            # Drop any staged tensors from the old device
            self._model.current_image = None
            self._model.current_hint = None
            self._device = target
            self.device_name = str(target)

    def switch_device(self, device: str) -> None:
        self.to_device(device)

    # ── Core single-pass colorize at fixed model size ─────────────────────

    def _colorize_at_size(self, rgb: np.ndarray, size: int,
                          denoise_sigma: int,
                          hint_points=None) -> np.ndarray:
        """Run mc-v2 once at *size*, returning float32 RGB [0,1]."""
        # fp16 autocast on CUDA: ~1.5-2x faster on tensor-core GPUs, half VRAM
        with torch.inference_mode(), torch.autocast(
                device_type="cuda", dtype=torch.float16,
                enabled=self._device.type == "cuda"):
            self._model.set_image(rgb, size=size,
                                  apply_denoise=denoise_sigma > 0,
                                  denoise_sigma=denoise_sigma)
            if hint_points:
                # Feed the guided-coloring palette into the model's native
                # hint channel — it propagates these colors with its own
                # learned shading instead of inventing a global wash
                hint, mask = build_hint_arrays(
                    rgb.shape[0], rgb.shape[1], size, hint_points)
                self._model.update_hint(hint, mask)
            return self._model.colorize()

    def _safe_colorize(self, rgb: np.ndarray, size: int,
                       denoise_sigma: int, hint_points=None) -> np.ndarray:
        """Robust single-pass colorize with shrink-then-CPU OOM fallback."""
        attempts = [size, max(384, size // 2)]
        last_err: RuntimeError | None = None
        for try_size in attempts:
            try:
                return self._colorize_at_size(rgb, try_size, denoise_sigma,
                                              hint_points=hint_points)
            except RuntimeError as exc:
                last_err = exc
                msg = str(exc).lower()
                if "out of memory" not in msg:
                    raise
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                gc.collect()
                continue

        # All GPU attempts OOM'd — fall back to CPU
        if self.device_name != "cpu":
            self._device = torch.device("cpu")
            self._model = MangaColorizator(
                device=self._device,
                generator_path=self._generator_path,
                extractor_path=self._extractor_path,
                denoiser_weights_dir=self._denoiser_weights_dir,
            )
            self.device_name = "cpu"
            return self._colorize_at_size(rgb, max(384, size // 2), denoise_sigma,
                                          hint_points=hint_points)

        raise last_err if last_err else RuntimeError("colorize failed")

    # ── Public colorize ────────────────────────────────────────────────────

    def colorize(self, image: np.ndarray, size: int = 576,
                 denoise_sigma: int = 18,
                 *,
                 tiled: bool = False,
                 tile_size: int = 768,
                 tile_overlap: int = 96,
                 per_panel: bool = False,
                 panel_style: str = "western",
                 deherron: bool = False,
                 deherron_strength: float = 0.6,
                 hint_points=None) -> np.ndarray:
        """Colorize a single B&W page image.

        Parameters
        ----------
        image : np.ndarray
            BGR uint8 input.
        size : int
            Target resize dimension (must be /32) for the simple path.
        denoise_sigma : int
            FFDNet denoiser strength (0-255).
        tiled : bool
            If True, run tiled colorization at native resolution and
            blend tiles with feathered alpha.
        tile_size, tile_overlap : int
            Tile size and overlap (pixels) for tiled mode.
        per_panel : bool
            If True, detect panels and colorize each independently.
        deherron : bool
            If True, soften screentones before the model sees the page.
        """
        # Ensure 3 channels (mc-v2 expects RGB)
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        elif image.shape[2] == 4:
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)

        if deherron:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            cleaned = deherron_screentones(gray, strength=deherron_strength)
            image = cv2.cvtColor(cleaned, cv2.COLOR_GRAY2BGR)

        # Tiled / per-panel paths: denoise the whole page ONCE up front
        # instead of re-denoising every (overlapping) tile or panel.
        if (tiled or per_panel) and denoise_sigma > 0:
            try:
                with torch.autocast(device_type="cuda", dtype=torch.float16,
                                    enabled=self._device.type == "cuda"):
                    image = self._model.denoiser.get_denoised_image(
                        image, sigma=denoise_sigma, max_edge=None)
                denoise_sigma = 0
            except RuntimeError as exc:
                if "out of memory" not in str(exc).lower():
                    raise
                # Page too large for one denoise pass — keep per-tile denoising
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

        if per_panel:
            return self._colorize_per_panel(
                image, size=size, denoise_sigma=denoise_sigma,
                tiled=tiled, tile_size=tile_size, tile_overlap=tile_overlap,
                panel_style=panel_style, hint_points=hint_points,
            )

        if tiled:
            # Tiled path doesn't support hints yet (tile-local remap TBD)
            return self._colorize_tiled(
                image, denoise_sigma=denoise_sigma,
                tile_size=tile_size, overlap=tile_overlap,
            )

        return self._colorize_simple(image, size=size, denoise_sigma=denoise_sigma,
                                     hint_points=hint_points)

    # ── Simple resize-and-go path (legacy) ─────────────────────────────────

    def _colorize_simple(self, image: np.ndarray, size: int,
                         denoise_sigma: int, hint_points=None) -> np.ndarray:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        orig_h, orig_w = rgb.shape[:2]

        with self._lock:
            result = self._safe_colorize(rgb, size, denoise_sigma,
                                         hint_points=hint_points)

        result_uint8 = np.clip(result * 255.0, 0, 255).astype(np.uint8)
        result_bgr = cv2.cvtColor(result_uint8, cv2.COLOR_RGB2BGR)

        if result_bgr.shape[:2] != (orig_h, orig_w):
            rh, rw = result_bgr.shape[:2]
            interp = cv2.INTER_AREA if (rh > orig_h or rw > orig_w) else cv2.INTER_LANCZOS4
            result_bgr = cv2.resize(result_bgr, (orig_w, orig_h), interpolation=interp)
        return result_bgr

    # ── Per-panel path ─────────────────────────────────────────────────────

    @staticmethod
    def _hints_for_panel(hint_points, panel, page_w: int, page_h: int):
        """Remap page-normalized hint points into panel-normalized coords."""
        if not hint_points:
            return None
        remapped = []
        for (xn, yn, rgb) in hint_points:
            px = xn * page_w
            py = yn * page_h
            if (panel.x <= px < panel.x + panel.width
                    and panel.y <= py < panel.y + panel.height):
                remapped.append(((px - panel.x) / panel.width,
                                 (py - panel.y) / panel.height, rgb))
        return remapped or None

    def _colorize_per_panel(self, image: np.ndarray, *,
                            size: int, denoise_sigma: int,
                            tiled: bool, tile_size: int, tile_overlap: int,
                            panel_style: str, hint_points=None) -> np.ndarray:
        """Detect panels, colorize each, composite back into the page."""
        from models.schemas import PanelRegion

        try:
            panels = detect_panels(image, style=panel_style)
        except Exception:
            panels = []

        # If detection found nothing useful, fall back to tiled or simple
        if not panels or len(panels) <= 1:
            if tiled:
                return self._colorize_tiled(image, denoise_sigma=denoise_sigma,
                                            tile_size=tile_size, overlap=tile_overlap)
            return self._colorize_simple(image, size=size, denoise_sigma=denoise_sigma,
                                         hint_points=hint_points)

        page_h, page_w = image.shape[:2]
        out = image.copy()
        for panel in panels:
            crop = extract_panel_image(image, panel)
            if crop.size == 0:
                continue
            ph, pw = crop.shape[:2]
            if min(ph, pw) < 64:
                continue

            panel_hints = self._hints_for_panel(hint_points, panel, page_w, page_h)

            if tiled and max(ph, pw) > tile_size:
                colored = self._colorize_tiled(
                    crop, denoise_sigma=denoise_sigma,
                    tile_size=tile_size, overlap=tile_overlap,
                )
            else:
                colored = self._colorize_simple(
                    crop, size=size, denoise_sigma=denoise_sigma,
                    hint_points=panel_hints,
                )

            # Composite back, with a small feather at the seam
            seam = self._panel_feather(ph, pw, feather=8)
            target = out[panel.y:panel.y + ph, panel.x:panel.x + pw].astype(np.float32)
            colored_f = colored.astype(np.float32)
            blended = colored_f * seam + target * (1.0 - seam)
            out[panel.y:panel.y + ph, panel.x:panel.x + pw] = np.clip(blended, 0, 255).astype(np.uint8)

        return out

    @staticmethod
    def _panel_feather(h: int, w: int, feather: int = 8) -> np.ndarray:
        """Soft 1.0 mask with a small fade at the borders."""
        feather = max(1, min(feather, min(h, w) // 4))
        m = np.ones((h, w), dtype=np.float32)
        for i in range(feather):
            v = (i + 1) / (feather + 1)
            if i < h:
                m[i, :] *= v
                m[h - 1 - i, :] *= v
            if i < w:
                m[:, i] *= v
                m[:, w - 1 - i] *= v
        return m[:, :, None]

    # ── Tiled native-resolution path ──────────────────────────────────────

    def _colorize_tiled(self, image: np.ndarray, *,
                        denoise_sigma: int,
                        tile_size: int = 768,
                        overlap: int = 96) -> np.ndarray:
        """Colorize at native resolution by tiling.

        Each tile is fed to mc-v2 at exactly *tile_size* (the model's
        native input size — no internal downsampling). Tiles overlap by
        ``overlap`` pixels and are composited with a feathered alpha so
        seams disappear.
        """
        h, w = image.shape[:2]

        # Round tile size to /32 (mc-v2 requirement)
        tile_size = max(384, (tile_size // 32) * 32)
        overlap = max(16, min(overlap, tile_size // 4))

        # If the page already fits in one tile, just run the simple path
        if h <= tile_size and w <= tile_size:
            return self._colorize_simple(image, size=tile_size, denoise_sigma=denoise_sigma)

        # Stride: how far we move each step
        stride = tile_size - overlap

        # Compute tile origins so the last tile lands on the edge
        def _origins(extent: int) -> list[int]:
            if extent <= tile_size:
                return [0]
            origins = list(range(0, extent - tile_size, stride))
            origins.append(extent - tile_size)
            return sorted(set(origins))

        ys = _origins(h)
        xs = _origins(w)

        accum = np.zeros((h, w, 3), dtype=np.float32)
        weight = np.zeros((h, w, 1), dtype=np.float32)

        # Per-tile feather alpha
        feather = self._tile_feather(tile_size, tile_size, overlap)

        for y in ys:
            for x in xs:
                tile_bgr = image[y:y + tile_size, x:x + tile_size]
                # Pad if at edge (model wants exactly tile_size)
                ph = tile_size - tile_bgr.shape[0]
                pw = tile_size - tile_bgr.shape[1]
                if ph > 0 or pw > 0:
                    tile_bgr = cv2.copyMakeBorder(tile_bgr, 0, ph, 0, pw,
                                                  cv2.BORDER_REFLECT)

                tile_rgb = cv2.cvtColor(tile_bgr, cv2.COLOR_BGR2RGB)
                with self._lock:
                    out = self._safe_colorize(tile_rgb, tile_size, denoise_sigma)
                out_u8 = np.clip(out * 255.0, 0, 255).astype(np.uint8)
                out_bgr = cv2.cvtColor(out_u8, cv2.COLOR_RGB2BGR)

                # Crop padding
                use_h = tile_size - ph
                use_w = tile_size - pw
                out_bgr = out_bgr[:use_h, :use_w]
                tile_alpha = feather[:use_h, :use_w]

                accum[y:y + use_h, x:x + use_w] += out_bgr.astype(np.float32) * tile_alpha
                weight[y:y + use_h, x:x + use_w] += tile_alpha

        weight = np.maximum(weight, 1e-6)
        return np.clip(accum / weight, 0, 255).astype(np.uint8)

    @staticmethod
    def _tile_feather(h: int, w: int, overlap: int) -> np.ndarray:
        """Cosine-tapered alpha mask (h, w, 1) peaking at center."""
        ramp_h = np.ones(h, dtype=np.float32)
        ramp_w = np.ones(w, dtype=np.float32)
        if overlap > 0:
            t = np.linspace(0.0, 1.0, overlap, dtype=np.float32)
            cos_in = 0.5 - 0.5 * np.cos(t * math.pi)
            ramp_h[:overlap] = cos_in
            ramp_h[-overlap:] = cos_in[::-1]
            ramp_w[:overlap] = cos_in
            ramp_w[-overlap:] = cos_in[::-1]
        return (ramp_h[:, None] * ramp_w[None, :])[:, :, None]

    def unload(self):
        """Release model and free GPU memory."""
        with self._lock:
            if self._model is not None:
                del self._model
                self._model = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
