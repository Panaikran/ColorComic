"""CLIP zero-shot region labeling — local semantics, no vision LLM.

Each segmented region's crop is compared against text prototypes
("a manga drawing of a character's hair", "…the sky", …) with the same
CLIP family already used for character memory.  This gives the palette
engine object identity (skin / hair / metal / sky / …) so a region can
receive a semantically sensible color instead of a model's guess.

Degrades gracefully: if CLIP can't load, ``available`` is False and the
guided pipeline simply produces no hints (previous behavior).
"""

import os

import cv2
import numpy as np


# (key, text used to build the CLIP prototype)
REGION_LABELS: list[tuple[str, str]] = [
    ("skin",     "a character's face or bare skin"),
    ("hair",     "a character's hair"),
    ("clothing", "clothing, a shirt, a dress or a fabric garment"),
    ("metal",    "metal armor, a sword, a weapon or machinery"),
    ("wood",     "wooden furniture, a wooden wall or a wooden floor"),
    ("sky",      "the sky or clouds"),
    ("foliage",  "trees, grass, bushes or plants"),
    ("stone",    "a stone wall, rocks or bricks"),
    ("water",    "water, a river or the sea"),
    ("fire",     "fire, flames or an explosion"),
    ("background", "the empty background of an indoor room"),
    ("bubble",   "a speech bubble filled with text"),
]

_PROMPT = "a black and white manga drawing of {}"


class RegionClassifier:
    """Zero-shot labeler for region crops (lazy CLIP load, batched)."""

    def __init__(self, model_path: str | None = None):
        self._model_path = model_path or os.environ.get(
            "GUIDED_CLIP_PATH", "openai/clip-vit-base-patch32")
        self._model = None
        self._processor = None
        self._text_embeds = None  # (n_labels, D), L2-normalized
        self._tried = False

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return self._model is not None

    def _ensure_loaded(self):
        if self._tried:
            return
        self._tried = True
        try:
            import torch
            from transformers import (
                CLIPImageProcessor,
                CLIPTokenizer,
                CLIPTextModelWithProjection,
                CLIPVisionModelWithProjection,
            )

            device = "cuda" if torch.cuda.is_available() else "cpu"
            # The *WithProjection variants return .text_embeds/.image_embeds
            # explicitly — stable across transformers versions (CLIPModel's
            # get_text_features return type is not)
            text_model = CLIPTextModelWithProjection.from_pretrained(
                self._model_path).to(device).eval()
            vision_model = CLIPVisionModelWithProjection.from_pretrained(
                self._model_path).to(device).eval()
            tokenizer = CLIPTokenizer.from_pretrained(self._model_path)
            processor = CLIPImageProcessor.from_pretrained(self._model_path)

            prompts = [_PROMPT.format(desc) for _, desc in REGION_LABELS]
            tokens = tokenizer(prompts, padding=True, return_tensors="pt")
            tokens = {k: v.to(device) for k, v in tokens.items()}
            with torch.inference_mode():
                text = text_model(**tokens).text_embeds
            text = text / text.norm(dim=-1, keepdim=True)

            # Text encoder is only needed once — free it immediately
            del text_model, tokenizer

            self._model = vision_model
            self._processor = processor
            self._text_embeds = text
            self._device = device
            print(f"[region_classifier] CLIP ready on {device}")
        except Exception as exc:
            print(f"[region_classifier] CLIP unavailable: {exc}")
            self._model = None

    def classify(self, page_bgr: np.ndarray, bboxes: list[tuple[int, int, int, int]],
                 ) -> list[tuple[str, float]] | None:
        """Label each bbox crop. Returns [(label_key, confidence)] or None.

        All crops go through CLIP in ONE batched forward.
        """
        self._ensure_loaded()
        if self._model is None or not bboxes:
            return None
        try:
            import torch

            crops = []
            H, W = page_bgr.shape[:2]
            for (x, y, w, h) in bboxes:
                x1, y1 = max(0, x), max(0, y)
                x2, y2 = min(W, x + w), min(H, y + h)
                crop = page_bgr[y1:y2, x1:x2]
                if crop.size == 0:
                    crop = page_bgr[:16, :16]
                crops.append(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))

            inputs = self._processor(images=crops, return_tensors="pt")
            pixel_values = inputs["pixel_values"].to(
                self._device, dtype=self._model.dtype)
            with torch.inference_mode():
                img = self._model(pixel_values=pixel_values).image_embeds
            img = img / img.norm(dim=-1, keepdim=True)

            # CLIP-standard temperature makes the softmax discriminative
            sims = (img @ self._text_embeds.T) * 100.0
            probs = sims.softmax(dim=-1).float().cpu().numpy()

            out: list[tuple[str, float]] = []
            for row in probs:
                idx = int(np.argmax(row))
                out.append((REGION_LABELS[idx][0], float(row[idx])))
            return out
        except Exception as exc:
            print(f"[region_classifier] classify failed: {exc}")
            return None
