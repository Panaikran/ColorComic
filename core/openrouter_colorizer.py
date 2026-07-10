"""OpenRouter image-to-image colorization adapter."""

from __future__ import annotations

import base64
import os
import re
from typing import Any

import cv2
import numpy as np
import requests


class OpenRouterColorizer:
    """Colorize comic pages through an OpenRouter image-output model."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        api_url: str,
        prompt: str,
        modalities: list[str],
        site_url: str = "",
        app_name: str = "ColorComic",
        max_input_edge: int = 1600,
        timeout: int = 300,
    ):
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required for LLM mode")
        if not model:
            raise ValueError("OPENROUTER_MODEL is required for LLM mode")

        self.api_key = api_key
        self.model = model
        self.api_url = api_url.rstrip("/")
        self.prompt = prompt
        self.modalities = modalities or ["image", "text"]
        self.site_url = site_url
        self.app_name = app_name
        self.max_input_edge = max(512, int(max_input_edge))
        self.timeout = int(timeout)
        self.device_name = "openrouter"
        self.cuda_available = False
        # Shared session for connection pooling; requests.Session is
        # thread-safe, so pages can be colorized concurrently (the API is
        # network-bound — no GPU to protect).
        self._session = requests.Session()

    def colorize(
        self,
        image: np.ndarray,
        *,
        style_label: str = "auto",
        style_prompt: str = "",
        reference_images: list[np.ndarray] | None = None,
    ) -> np.ndarray:
        """Return a BGR uint8 page colorized by OpenRouter."""
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        elif image.shape[2] == 4:
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)

        orig_h, orig_w = image.shape[:2]
        request_image = self._fit_for_request(image)
        content: list[dict[str, Any]] = [
            {"type": "text", "text": self._build_prompt(style_label, style_prompt)}
        ]
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": self._image_to_data_url(request_image)},
            }
        )

        if reference_images:
            for ref in reference_images[:4]:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": self._image_to_data_url(self._fit_for_request(ref))},
                    }
                )

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "modalities": self.modalities,
            "stream": False,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        if self.app_name:
            headers["X-Title"] = self.app_name

        response = self._session.post(
            f"{self.api_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )

        if response.status_code >= 400:
            raise RuntimeError(
                f"OpenRouter request failed ({response.status_code}): {response.text[:500]}"
            )

        data = response.json()
        data_url = self._extract_image_data_url(data)
        result = self._data_url_to_bgr(data_url)
        if result.shape[:2] != (orig_h, orig_w):
            result = cv2.resize(result, (orig_w, orig_h), interpolation=cv2.INTER_LANCZOS4)
        return result

    def unload(self) -> None:
        return None

    def _build_prompt(self, style_label: str, style_prompt: str) -> str:
        extra = []
        if style_label and style_label != "auto":
            extra.append(f"Reading/art direction: {style_label}.")
        if style_prompt:
            extra.append(f"Style preset: {style_prompt}.")
        suffix = "\n".join(extra)
        if suffix:
            return f"{self.prompt}\n\n{suffix}"
        return self.prompt

    def _fit_for_request(self, image: np.ndarray) -> np.ndarray:
        h, w = image.shape[:2]
        edge = max(h, w)
        if edge <= self.max_input_edge:
            return image
        scale = self.max_input_edge / edge
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

    @staticmethod
    def _image_to_data_url(image: np.ndarray) -> str:
        # JPEG q90 is ~5-10x smaller than PNG for scanned pages — much
        # faster request serialization and upload
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            raise ValueError("Could not encode image for OpenRouter")
        b64 = base64.b64encode(encoded.tobytes()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"

    @staticmethod
    def _extract_image_data_url(data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"OpenRouter returned no choices: {data}")

        message = choices[0].get("message") or {}
        images = message.get("images") or []
        if images:
            first = images[0]
            image_url = first.get("image_url") or first.get("imageUrl") or {}
            url = image_url.get("url") if isinstance(image_url, dict) else None
            if url:
                return url

        content = message.get("content")
        if isinstance(content, list):
            for part in content:
                image_url = part.get("image_url") or part.get("imageUrl") or {}
                url = image_url.get("url") if isinstance(image_url, dict) else None
                if url:
                    return url
        elif isinstance(content, str):
            match = re.search(r"data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=\s]+", content)
            if match:
                return re.sub(r"\s+", "", match.group(0))

        raise RuntimeError(f"OpenRouter response did not include an image: {data}")

    @staticmethod
    def _data_url_to_bgr(data_url: str) -> np.ndarray:
        if not data_url.startswith("data:image/"):
            raise RuntimeError("OpenRouter returned an image URL instead of embedded image data")
        _, b64 = data_url.split(",", 1)
        blob = base64.b64decode(b64)
        arr = np.frombuffer(blob, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("Could not decode OpenRouter image response")
        return img


def build_openrouter_colorizer(config) -> OpenRouterColorizer:
    return OpenRouterColorizer(
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        model=config.OPENROUTER_MODEL,
        api_url=config.OPENROUTER_API_URL,
        prompt=config.OPENROUTER_PROMPT,
        modalities=config.OPENROUTER_MODALITIES,
        site_url=config.OPENROUTER_SITE_URL,
        app_name=config.OPENROUTER_APP_NAME,
        max_input_edge=config.OPENROUTER_MAX_INPUT_EDGE,
        timeout=config.OPENROUTER_TIMEOUT,
    )
