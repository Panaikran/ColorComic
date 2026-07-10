"""VRAM-aware model manager — only one colorizer on the GPU at a time.

Designed for 8 GB GPUs where mc-v2 (~3 GB) and MangaNinja (~6 GB)
cannot coexist simultaneously.  Evicted models are parked on CPU RAM
(not destroyed) so switching modes back is seconds, not minutes.
"""

import gc
import threading

import torch

from config import Config
from core.ml_colorizer import MangaColorizer


class ModelManager:
    """Manages exclusive loading of colorizer models to fit in VRAM.

    Usage::

        manager = ModelManager(device="auto")
        colorizer = manager.get_colorizer("auto")       # loads mc-v2
        colorizer = manager.get_colorizer("reference")   # parks mc-v2 on CPU, loads MangaNinja
    """

    def __init__(self, device: str = "auto"):
        self._lock = threading.Lock()
        self._device = device
        self._current_mode: str | None = None
        self._colorizer = None  # MangaColorizer or MangaNinjaColorizer
        self._parked: dict[str, object] = {}  # mode -> CPU-parked colorizer

    @property
    def current_mode(self) -> str | None:
        return self._current_mode

    @property
    def device_name(self) -> str:
        if self._colorizer is not None and hasattr(self._colorizer, "device_name"):
            return self._colorizer.device_name
        dev = self._resolve_device()
        return str(dev)

    @property
    def cuda_available(self) -> bool:
        return torch.cuda.is_available()

    def _resolve_device(self, device: str | None = None) -> torch.device:
        dev = self._device if device is None else device
        if dev == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        return torch.device(dev)

    def get_colorizer(self, mode: str = "auto"):
        """Return the colorizer for *mode*, loading it if necessary.

        If a different mode is currently loaded, it is parked on CPU first
        to free VRAM.  A previously parked model for *mode* is revived by
        moving it back to the target device instead of reloading from disk.

        Parameters
        ----------
        mode : str
            ``"auto"`` for manga-colorization-v2, ``"reference"`` for MangaNinja.
        """
        with self._lock:
            if self._current_mode == mode and self._colorizer is not None:
                return self._colorizer

            # Park the current model on CPU (keeps weights in RAM)
            self._park_current()

            # Revive a parked model if we have one for this mode
            parked = self._parked.pop(mode, None)
            if parked is not None:
                try:
                    if hasattr(parked, "to_device"):
                        parked.to_device(str(self._resolve_device()))
                    self._colorizer = parked
                except Exception as exc:  # revive failed — fall back to fresh load
                    print(f"[ModelManager] revive of parked {mode!r} failed ({exc}); reloading")
                    self._destroy(parked)
                    self._colorizer = None

            if self._colorizer is None:
                if mode == "auto":
                    self._colorizer = self._load_mcv2()
                elif mode == "reference":
                    self._colorizer = self._load_manganinja()
                elif mode == "llm":
                    self._colorizer = self._load_openrouter()
                else:
                    raise ValueError(f"Unknown colorization mode: {mode!r}")

            self._current_mode = mode
            return self._colorizer

    def switch_device(self, device: str):
        """Change the target device. Moves the current model if needed.

        Compares *resolved* devices — "auto" on a CUDA box and "cuda" are
        the same physical device, so no reload happens.
        """
        with self._lock:
            if self._resolve_device(device) == self._resolve_device():
                self._device = device  # remember the label, nothing to move
                return
            self._device = device
            target = self._resolve_device()
            if self._colorizer is not None:
                if hasattr(self._colorizer, "to_device"):
                    self._colorizer.to_device(str(target))
                elif hasattr(self._colorizer, "switch_device"):
                    self._colorizer.switch_device(str(target))
            self._flush_vram()

    def _park_current(self):
        """Move the active colorizer to CPU RAM and remember it."""
        if self._colorizer is None:
            return
        mode = self._current_mode
        colorizer = self._colorizer
        self._colorizer = None
        self._current_mode = None
        try:
            if mode is not None and hasattr(colorizer, "to_device"):
                colorizer.to_device("cpu")
                self._parked[mode] = colorizer
            else:
                self._destroy(colorizer)
        except Exception as exc:
            print(f"[ModelManager] CPU-park of {mode!r} failed ({exc}); unloading")
            self._destroy(colorizer)
        self._flush_vram()

    @staticmethod
    def _destroy(colorizer):
        try:
            if hasattr(colorizer, "unload"):
                colorizer.unload()
        except Exception:
            pass

    @staticmethod
    def _flush_vram():
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def _load_mcv2(self) -> MangaColorizer:
        """Load the manga-colorization-v2 model."""
        from core.model_downloader import ensure_models_downloaded

        ensure_models_downloaded(Config.WEIGHTS_DIR, callback=print)
        colorizer = MangaColorizer(
            device=self._device,
            generator_path=Config.GENERATOR_WEIGHTS_PATH,
            extractor_path=Config.EXTRACTOR_WEIGHTS_PATH,
            denoiser_weights_dir=Config.DENOISER_WEIGHTS_DIR,
        )
        print(f"[ModelManager] mc-v2 loaded on {colorizer.device_name}")
        return colorizer

    def _load_manganinja(self):
        """Load the MangaNinja reference-based colorizer."""
        from core.model_downloader import ensure_manganinja_downloaded
        from core.manga_ninja_colorizer import MangaNinjaColorizer

        ensure_manganinja_downloaded(Config, callback=print)
        colorizer = MangaNinjaColorizer(
            device=self._device,
            config=Config,
        )
        print(f"[ModelManager] MangaNinja loaded on {colorizer.device_name}")
        return colorizer

    def _load_openrouter(self):
        """Load the OpenRouter API-backed colorizer."""
        from core.openrouter_colorizer import build_openrouter_colorizer

        colorizer = build_openrouter_colorizer(Config)
        print(f"[ModelManager] OpenRouter image mode ready: {Config.OPENROUTER_MODEL}")
        return colorizer
