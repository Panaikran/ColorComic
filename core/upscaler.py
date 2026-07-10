"""Real-ESRGAN 4x upscaler — self-contained, no basicsr/realesrgan dependency.

Implements only the RRDBNet architecture and tiled inference needed for
the ``RealESRGAN_x4plus_anime_6B`` model (~17 MB, 6 RRDB blocks).
"""

import gc
import math
import os
import threading

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# ── Minimal RRDBNet architecture ─────────────────────────────────────────────


class ResidualDenseBlock(nn.Module):
    def __init__(self, num_feat: int = 64, num_grow_ch: int = 32):
        super().__init__()
        self.conv1 = nn.Conv2d(num_feat, num_grow_ch, 3, 1, 1)
        self.conv2 = nn.Conv2d(num_feat + num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv3 = nn.Conv2d(num_feat + 2 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv4 = nn.Conv2d(num_feat + 3 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv5 = nn.Conv2d(num_feat + 4 * num_grow_ch, num_feat, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x1 = self.lrelu(self.conv1(x))
        x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
        x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
        x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
        x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
        return x5 * 0.2 + x


class RRDB(nn.Module):
    def __init__(self, num_feat: int, num_grow_ch: int = 32):
        super().__init__()
        self.rdb1 = ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb2 = ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb3 = ResidualDenseBlock(num_feat, num_grow_ch)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.rdb1(x)
        out = self.rdb2(out)
        out = self.rdb3(out)
        return out * 0.2 + x


class RRDBNet(nn.Module):
    """Residual-in-Residual Dense Block Network for super-resolution.

    Module names match the upstream Real-ESRGAN ``RRDBNet`` so
    ``RealESRGAN_x4plus_anime_6B.pth`` loads with ``strict=True``.
    Only ``scale=4`` is supported (standard anime checkpoint).
    """

    def __init__(self, num_in_ch: int = 3, num_out_ch: int = 3,
                 scale: int = 4, num_feat: int = 64,
                 num_block: int = 6, num_grow_ch: int = 32):
        super().__init__()
        if scale != 4:
            raise ValueError(f"Only scale=4 is supported, got {scale}")
        self.scale = scale

        self.conv_first = nn.Conv2d(num_in_ch, num_feat, 3, 1, 1)
        self.body = nn.Sequential(*(RRDB(num_feat, num_grow_ch) for _ in range(num_block)))
        self.conv_body = nn.Conv2d(num_feat, num_feat, 3, 1, 1)

        # Upsampling — two nearest-neighbor + conv stages for x4 scale
        self.conv_up1 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_up2 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)

        self.conv_hr = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_last = nn.Conv2d(num_feat, num_out_ch, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        feat = self.conv_first(x)
        body_feat = self.conv_body(self.body(feat))
        feat = feat + body_feat

        feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
        feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))

        out = self.conv_last(self.lrelu(self.conv_hr(feat)))
        return out


# ── Tiled inference helper ───────────────────────────────────────────────────


def _tile_process(model: RRDBNet, img: torch.Tensor, scale: int,
                  tile_size: int, tile_pad: int, device) -> torch.Tensor:
    """Run *model* on *img* using overlapping tiles to limit VRAM."""
    # One H2D transfer for the whole image; tiles are sliced on-device
    img = img.to(device)
    batch, channel, height, width = img.shape
    out_h, out_w = height * scale, width * scale

    # Accumulate on GPU to avoid per-tile PCIe transfers
    output = torch.zeros(batch, channel, out_h, out_w,
                         dtype=img.dtype, device=device)

    tiles_x = math.ceil(width / tile_size)
    tiles_y = math.ceil(height / tile_size)

    for y in range(tiles_y):
        for x in range(tiles_x):
            # Input tile boundaries
            x_start = x * tile_size
            y_start = y * tile_size
            x_end = min(x_start + tile_size, width)
            y_end = min(y_start + tile_size, height)

            # Add padding
            x_start_pad = max(x_start - tile_pad, 0)
            y_start_pad = max(y_start - tile_pad, 0)
            x_end_pad = min(x_end + tile_pad, width)
            y_end_pad = min(y_end + tile_pad, height)

            tile = img[:, :, y_start_pad:y_end_pad, x_start_pad:x_end_pad]
            out_tile = model(tile)

            # Output tile boundaries (scaled)
            ox_start = (x_start - x_start_pad) * scale
            oy_start = (y_start - y_start_pad) * scale
            ox_end = ox_start + (x_end - x_start) * scale
            oy_end = oy_start + (y_end - y_start) * scale

            # Destination in full output — stays on GPU
            dx_start = x_start * scale
            dy_start = y_start * scale
            dx_end = x_end * scale
            dy_end = y_end * scale

            output[:, :, dy_start:dy_end, dx_start:dx_end] = \
                out_tile[:, :, oy_start:oy_end, ox_start:ox_end]

            del tile, out_tile

    return output


# ── Public Upscaler class ────────────────────────────────────────────────────


class Upscaler:
    """Wraps Real-ESRGAN for 4x anime-optimized upscaling.

    Model is loaded lazily on the first call to :meth:`upscale`.
    Weights are auto-downloaded if missing.
    """

    def __init__(self, *, model_path: str, model_url: str, scale: int = 4,
                 tile: int = 256, device: str = "auto"):
        self._model_path = model_path
        self._model_url = model_url
        self._scale = scale
        self._tile = tile
        self._device_str = device
        self._model: RRDBNet | None = None
        self._lock = threading.Lock()

    def _resolve_device(self):
        if self._device_str == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        return torch.device(self._device_str)

    def _ensure_weights(self):
        if os.path.exists(self._model_path):
            return
        os.makedirs(os.path.dirname(self._model_path), exist_ok=True)
        import urllib.request
        print(f"Downloading Real-ESRGAN weights to {self._model_path}...")
        urllib.request.urlretrieve(self._model_url, self._model_path)
        print("Real-ESRGAN weights downloaded.")

    def _load_model(self):
        self._ensure_weights()
        device = self._resolve_device()

        net = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64,
                      num_block=6, num_grow_ch=32, scale=self._scale)

        state = torch.load(self._model_path, map_location="cpu", weights_only=True)
        # Some checkpoints wrap in 'params_ema' or 'params'
        if "params_ema" in state:
            state = state["params_ema"]
        elif "params" in state:
            state = state["params"]

        net.load_state_dict(state, strict=True)
        net.eval()

        if device.type == "cuda":
            net = net.half().to(device)
        else:
            net = net.to(device)

        self._model = net
        self._device = device
        print(f"[Upscaler] Real-ESRGAN loaded on {device}")

    @torch.inference_mode()
    def upscale(self, image: np.ndarray) -> np.ndarray:
        """Upscale a BGR uint8 image by the configured scale factor."""
        with self._lock:
            if self._model is None:
                self._load_model()

            # BGR uint8 -> RGB float tensor (contiguous for efficient transfer)
            img = np.ascontiguousarray(image[:, :, ::-1]).astype(np.float32) / 255.0
            img_t = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0).contiguous()

            if self._device.type == "cuda":
                img_t = img_t.half()

            output = _tile_process(
                self._model, img_t, self._scale,
                self._tile, tile_pad=10, device=self._device,
            )
            del img_t

            # Convert to uint8 ON the device — the PCIe transfer is then 4x
            # smaller than shipping fp32 (and 2x smaller than fp16)
            output = (output.squeeze(0).clamp_(0, 1)
                      .mul_(255.0).add_(0.5).to(torch.uint8).cpu())
            result = output.permute(1, 2, 0).numpy()
            del output
            return np.ascontiguousarray(result[:, :, ::-1])  # RGB -> BGR

    def to_device(self, device: str):
        """Move the loaded model between devices without reloading."""
        with self._lock:
            self._device_str = device
            if self._model is not None:
                target = self._resolve_device()
                if target != self._device:
                    if target.type == "cuda":
                        self._model = self._model.half().to(target)
                    else:
                        self._model = self._model.float().to(target)
                    self._device = target

    def unload(self):
        """Free GPU memory used by the upscaler model."""
        with self._lock:
            if self._model is not None:
                del self._model
                self._model = None
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()


# ── Shared singleton ─────────────────────────────────────────────────────────
# Real-ESRGAN weights are re-read from disk and re-uploaded to the GPU for
# every fresh Upscaler — share one instance across jobs and retries.

_shared_upscaler: Upscaler | None = None
_shared_lock = threading.Lock()


def get_shared_upscaler(*, model_path: str, model_url: str, scale: int = 4,
                        tile: int = 512, device: str = "auto") -> Upscaler:
    """Return the process-wide shared Upscaler (created on first use)."""
    global _shared_upscaler
    with _shared_lock:
        if _shared_upscaler is None:
            _shared_upscaler = Upscaler(
                model_path=model_path, model_url=model_url,
                scale=scale, tile=tile, device=device,
            )
        elif _shared_upscaler._device_str != device:
            _shared_upscaler.to_device(device)
        return _shared_upscaler
