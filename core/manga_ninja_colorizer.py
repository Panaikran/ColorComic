"""MangaNinja reference-based colorizer wrapper.

Loads the MangaNinja pipeline (SD 1.5 + Reference UNet + Denoising UNet +
ControlNet + CLIP + PointNet) and provides a ``colorize()`` interface
matching :class:`MangaColorizer`.

Adds:
- Multi-reference support (best-of by CLIP similarity / fallback nearest).
- Optional second refine pass (SDEdit-style) at higher fidelity.
- SDPA attention enabled where possible.

Licensed under CC BY-NC 4.0 — non-commercial use only.
"""

import gc
import threading

import cv2
import numpy as np
import PIL.Image
import torch


class MangaNinjaColorizer:
    """Reference-based manga colorization using MangaNinja (CVPR 2025).

    Usage::

        colorizer = MangaNinjaColorizer(device="auto", config=Config)
        result_bgr = colorizer.colorize(bgr_image, reference_image=ref_bgr)
        # or with multiple references:
        result_bgr = colorizer.colorize(bgr_image, reference_images=[ref1, ref2])
    """

    def __init__(self, device: str = "auto", config=None):
        self._lock = threading.Lock()
        self._device = self._resolve_device(device)
        self._config = config
        self._pipeline = None
        self._clip_model = None  # for multi-ref selection
        self._clip_proc = None
        self.device_name = str(self._device)
        self.cuda_available = torch.cuda.is_available()

        # Per-reference caches (reused across pages within a job):
        # ref-key -> CLIP embedding / chroma score for selection;
        # (ref-key, size) -> pipeline-side encoder cache (CLIP/text/VAE latents).
        self._ref_emb_cache: dict[str, np.ndarray | None] = {}
        self._ref_chroma_cache: dict[str, float] = {}
        self._pipe_ref_caches: dict[tuple[str, int], dict] = {}

        self._load_pipeline()

    @staticmethod
    def _resolve_device(device: str):
        if device == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        return torch.device(device)

    @staticmethod
    def _build_from_checkpoint(model_cls, pretrained_path: str, subfolder: str | None,
                               ckpt_path: str, label: str, **config_overrides):
        """Build a diffusers model and load its fine-tuned checkpoint.

        Fast path: when the checkpoint fully covers the model's parameters,
        construct from config only (no base-weight read) and load the
        checkpoint directly.  Falls back to from_pretrained + overlay when
        the checkpoint is partial (matches the previous behavior).
        """
        print(f"[MangaNinja] Loading {label} weights...")
        state = torch.load(ckpt_path, map_location="cpu")

        kwargs = {"subfolder": subfolder} if subfolder else {}
        config = model_cls.load_config(pretrained_path, **kwargs)
        config = dict(config)
        config.update(config_overrides)
        model = model_cls.from_config(config)

        missing = [k for k in model.state_dict().keys() if k not in state]
        if missing:
            # Partial checkpoint — base weights are needed for the gaps.
            print(f"[MangaNinja] {label}: checkpoint misses {len(missing)} keys; "
                  "loading base weights first")
            model = model_cls.from_pretrained(
                pretrained_path, low_cpu_mem_usage=False,
                ignore_mismatched_sizes=True, **kwargs, **config_overrides,
            )
            model.load_state_dict(state, strict=False)
        else:
            try:
                model.load_state_dict(state, strict=False, assign=True)
            except TypeError:  # torch < 2.1 has no assign kwarg
                model.load_state_dict(state, strict=False)
        del state
        return model

    def _load_pipeline(self):
        """Load the full MangaNinja pipeline."""
        from diffusers import (
            AutoencoderKL,
            ControlNetModel,
            DPMSolverMultistepScheduler,
        )
        from transformers import (
            CLIPImageProcessor,
            CLIPTextModel,
            CLIPTokenizer,
            CLIPVisionModelWithProjection,
        )
        from vendor.manganinja.pipeline import MangaNinjiaPipeline
        from vendor.manganinja.models.unet_2d_condition import UNet2DConditionModel
        from vendor.manganinja.models.refunet_2d_condition import RefUNet2DConditionModel
        from vendor.manganinja.point_network import PointNet
        from vendor.manganinja.annotator.lineart import BatchLineartDetector

        cfg = self._config
        device = self._device
        dtype = torch.float16 if device.type == "cuda" else torch.float32

        print("[MangaNinja] Loading SD 1.5 components...")

        # DPM-Solver++ reaches DDIM@30 quality in ~14-16 steps (~2x faster)
        scheduler = DPMSolverMultistepScheduler.from_pretrained(
            cfg.SD15_MODEL_PATH, subfolder="scheduler",
            algorithm_type="dpmsolver++", use_karras_sigmas=True,
        )
        vae = AutoencoderKL.from_pretrained(
            cfg.SD15_MODEL_PATH, subfolder="vae", torch_dtype=dtype,
        )

        denoising_unet = self._build_from_checkpoint(
            UNet2DConditionModel, cfg.SD15_MODEL_PATH, "unet",
            cfg.MANGANINJA_DENOISING_UNET, "denoising UNet", in_channels=4,
        )
        reference_unet = self._build_from_checkpoint(
            RefUNet2DConditionModel, cfg.SD15_MODEL_PATH, "unet",
            cfg.MANGANINJA_REFERENCE_UNET, "reference UNet", in_channels=4,
        )
        controlnet = self._build_from_checkpoint(
            ControlNetModel, cfg.CONTROLNET_LINEART_PATH, None,
            cfg.MANGANINJA_CONTROLNET, "ControlNet", in_channels=4,
        )

        print("[MangaNinja] Loading CLIP...")
        tokenizer = CLIPTokenizer.from_pretrained(cfg.CLIP_VISION_PATH)
        text_encoder = CLIPTextModel.from_pretrained(cfg.CLIP_VISION_PATH, torch_dtype=dtype)
        image_encoder = CLIPVisionModelWithProjection.from_pretrained(
            cfg.CLIP_VISION_PATH, torch_dtype=dtype,
        )

        point_net = PointNet()
        state = torch.load(cfg.MANGANINJA_POINTNET, map_location="cpu")
        point_net.load_state_dict(state, strict=False)
        del state

        preprocessor = BatchLineartDetector(cfg.LINEART_ANNOTATOR_PATH)
        preprocessor.to(device, dtype=torch.float32)

        self._pipeline = MangaNinjiaPipeline(
            vae=vae,
            reference_unet=reference_unet,
            denoising_unet=denoising_unet,
            controlnet=controlnet,
            scheduler=scheduler,
            refnet_tokenizer=tokenizer,
            refnet_text_encoder=text_encoder,
            refnet_image_encoder=image_encoder,
            controlnet_tokenizer=tokenizer,
            controlnet_text_encoder=text_encoder,
            controlnet_image_encoder=image_encoder,
            point_net=point_net,
            preprocessor=preprocessor,
        )

        self._pipeline = self._pipeline.to(device=device, dtype=dtype)

        # NOTE: the vendored attention blocks already default to an SDPA
        # processor; swapping in diffusers' AttnProcessor2_0 would silently
        # drop their point-guidance (encoder_hidden_states_v) support.

        # Cache CLIP for multi-reference selection (separate from pipeline's)
        self._clip_model = image_encoder
        try:
            from transformers import CLIPImageProcessor
            self._clip_proc = CLIPImageProcessor.from_pretrained(cfg.CLIP_VISION_PATH)
        except Exception:
            self._clip_proc = None

        print(f"[MangaNinja] Pipeline loaded on {device}")

    # ── Multi-reference selection ─────────────────────────────────────────

    @staticmethod
    def _ref_key(image_bgr: np.ndarray) -> str:
        """Cheap stable key for a reference image (subsampled hash)."""
        import hashlib
        sub = image_bgr[::64, ::64]
        return hashlib.md5(
            sub.tobytes() + str(image_bgr.shape).encode()
        ).hexdigest()

    def _embed_image(self, image_bgr: np.ndarray) -> np.ndarray | None:
        if self._clip_model is None or self._clip_proc is None:
            return None
        try:
            rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            inputs = self._clip_proc(images=rgb, return_tensors="pt")
            # Match the encoder's dtype — fp16 CLIP rejects fp32 pixel_values
            pixel_values = inputs["pixel_values"].to(
                self._device, dtype=self._clip_model.dtype)
            with torch.inference_mode():
                emb = self._clip_model(pixel_values=pixel_values).image_embeds[0]
            v = emb.detach().float().cpu().numpy()
            n = float(np.linalg.norm(v)) + 1e-8
            return v / n
        except Exception:
            return None

    def _embed_reference(self, ref_bgr: np.ndarray) -> np.ndarray | None:
        """CLIP-embed a reference, cached across pages."""
        key = self._ref_key(ref_bgr)
        if key not in self._ref_emb_cache:
            if len(self._ref_emb_cache) > 32:
                self._ref_emb_cache.clear()
            self._ref_emb_cache[key] = self._embed_image(ref_bgr)
        return self._ref_emb_cache[key]

    def _ref_chroma(self, ref_bgr: np.ndarray) -> float:
        """Mean LAB chroma of a reference, cached across pages."""
        key = self._ref_key(ref_bgr)
        if key not in self._ref_chroma_cache:
            if len(self._ref_chroma_cache) > 32:
                self._ref_chroma_cache.clear()
            lab = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
            a = lab[:, :, 1] - 128.0
            b = lab[:, :, 2] - 128.0
            self._ref_chroma_cache[key] = float(np.sqrt(a * a + b * b).mean())
        return self._ref_chroma_cache[key]

    def _pick_reference(self, target_bgr: np.ndarray,
                        refs_bgr: list[np.ndarray]) -> np.ndarray:
        """Pick the best reference for a given target page."""
        if len(refs_bgr) == 1:
            return refs_bgr[0]

        target_emb = self._embed_image(target_bgr)
        if target_emb is None:
            # No CLIP — pick the most colorful reference (highest LAB chroma)
            best_idx = max(range(len(refs_bgr)),
                           key=lambda i: self._ref_chroma(refs_bgr[i]))
            return refs_bgr[best_idx]

        best_idx = 0
        best_sim = -1e9
        for i, r in enumerate(refs_bgr):
            r_emb = self._embed_reference(r)
            if r_emb is None:
                continue
            sim = float(np.dot(target_emb, r_emb))
            if sim > best_sim:
                best_sim = sim
                best_idx = i
        return refs_bgr[best_idx]

    # ── Public colorize ────────────────────────────────────────────────────

    def colorize(self, image: np.ndarray, reference_image: np.ndarray | None = None,
                 size: int = 512,
                 *,
                 reference_images: list[np.ndarray] | None = None,
                 num_inference_steps: int | None = None,
                 refine_pass: bool = False) -> np.ndarray:
        """Colorize a single B&W page using one or more colored references.

        Parameters
        ----------
        image : np.ndarray
            Grayscale input page in BGR uint8.
        reference_image : np.ndarray, optional
            Single reference (legacy single-ref API).
        reference_images : list[np.ndarray], optional
            Multi-reference list; if provided, the closest by CLIP is used.
        size : int
            Processing resolution (512 recommended).
        num_inference_steps : int, optional
            Override the configured step count.
        refine_pass : bool
            If True, run a second pass to sharpen detail.
        """
        # Pick reference
        if reference_images:
            ref = self._pick_reference(image, reference_images)
        elif reference_image is not None:
            ref = reference_image
        else:
            raise ValueError("MangaNinja requires reference_image or reference_images")

        orig_h, orig_w = image.shape[:2]
        steps = int(num_inference_steps or self._config.MANGANINJA_DENOISE_STEPS)

        target_pil = PIL.Image.fromarray(image[:, :, ::-1])
        ref_pil = PIL.Image.fromarray(ref[:, :, ::-1])

        # Pipeline-side encoder cache — reused for every page that shares
        # this reference (skips CLIP/text/VAE encoder passes per page).
        ref_key = self._ref_key(ref)

        with self._lock:
            with torch.inference_mode():
                result_rgb = self._pipeline(
                    ref_image=ref_pil,
                    target_image=target_pil,
                    num_inference_steps=steps,
                    width=size,
                    height=size,
                    ref_cache=self._get_pipe_ref_cache(ref_key, size),
                )

                if refine_pass:
                    # Lightweight second pass at higher size — feed the
                    # initial result back as the target to sharpen detail.
                    refine_size = min(768, max(size, 640))
                    refine_in = PIL.Image.fromarray(result_rgb).resize(
                        (refine_size, refine_size), PIL.Image.LANCZOS,
                    )
                    try:
                        result_rgb = self._pipeline(
                            ref_image=ref_pil,
                            target_image=refine_in,
                            num_inference_steps=max(8, steps // 2),
                            width=refine_size,
                            height=refine_size,
                            ref_cache=self._get_pipe_ref_cache(ref_key, refine_size),
                        )
                    except Exception as exc:
                        print(f"[MangaNinja] refine pass skipped: {exc}")

        result_bgr = cv2.cvtColor(result_rgb, cv2.COLOR_RGB2BGR)

        if result_bgr.shape[:2] != (orig_h, orig_w):
            rh, rw = result_bgr.shape[:2]
            interp = cv2.INTER_AREA if (rh > orig_h or rw > orig_w) else cv2.INTER_LANCZOS4
            result_bgr = cv2.resize(result_bgr, (orig_w, orig_h), interpolation=interp)
        return result_bgr

    def _get_pipe_ref_cache(self, ref_key: str, size: int) -> dict:
        """Mutable per-(reference, size) cache dict handed to the pipeline."""
        key = (ref_key, size)
        if key not in self._pipe_ref_caches:
            if len(self._pipe_ref_caches) > 8:
                self._pipe_ref_caches.clear()
            self._pipe_ref_caches[key] = {}
        return self._pipe_ref_caches[key]

    def to_device(self, device: str):
        """Move the pipeline between devices without reloading weights."""
        target = self._resolve_device(device)
        if str(target) == self.device_name:
            return
        with self._lock:
            self._pipeline = self._pipeline.to(target)
            try:
                self._pipeline.preprocessor.to(target)
            except Exception:
                pass
            # Cached latents live on the old device — drop them
            self._pipe_ref_caches.clear()
            self._device = target
            self.device_name = str(target)

    def unload(self):
        """Release pipeline and free GPU memory."""
        with self._lock:
            if self._pipeline is not None:
                del self._pipeline
                self._pipeline = None
            self._clip_model = None
            self._clip_proc = None
            self._ref_emb_cache.clear()
            self._ref_chroma_cache.clear()
            self._pipe_ref_caches.clear()
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
