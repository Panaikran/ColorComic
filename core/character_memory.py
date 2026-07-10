"""Per-character color memory.

Tracks faces across pages, clusters them into characters, and stores a
LAB color signature per character (mean A/B for skin and clothes).  On
later pages, we apply the stored signature only inside the matched
character's region rather than to the whole page.

Optional dependencies:
- ``mediapipe`` or ``opencv`` Haar cascade for face detection.
- ``transformers`` + ``torch`` for CLIP image embeddings.

If those aren't available, the manager degrades to a no-op so the
pipeline keeps working.  Use :pyattr:`enabled` to check at runtime.
"""

import os
from dataclasses import dataclass, field

import cv2
import numpy as np


# ── Optional CLIP backbone (lazy-loaded) ────────────────────────────────────


_CLIP_MODEL = None
_CLIP_PROCESSOR = None
_CLIP_DEVICE = "cpu"


def _try_load_clip():
    """Try to load a CLIP image encoder.  Returns (model, processor) or (None, None).

    Uses ``CLIPVisionModelWithProjection`` (vision-only) so the call site
    cannot accidentally get the full text+vision tuple.
    """
    global _CLIP_MODEL, _CLIP_PROCESSOR, _CLIP_DEVICE
    if _CLIP_MODEL is not None:
        return _CLIP_MODEL, _CLIP_PROCESSOR
    try:
        import torch
        from transformers import CLIPVisionModelWithProjection, CLIPImageProcessor
        name = os.environ.get("CHARACTER_CLIP_PATH", "openai/clip-vit-base-patch32")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = CLIPVisionModelWithProjection.from_pretrained(name).to(device).eval()
        processor = CLIPImageProcessor.from_pretrained(name)
        _CLIP_MODEL = model
        _CLIP_PROCESSOR = processor
        _CLIP_DEVICE = device
        return model, processor
    except Exception as exc:
        print(f"[character_memory] CLIP unavailable: {exc}")
        return None, None


# ── Face detection ──────────────────────────────────────────────────────────


# Max edge for detection — Haar cost scales with the image pyramid, so a
# 1280px copy is ~40x cheaper than a 4x-upscaled page with the same boxes.
_DETECT_MAX_EDGE = 1280

_HAAR_DETECTOR = None
_HAAR_TRIED = False


def _haar_face_detector():
    """Load OpenCV's bundled Haar cascade once (parsing the XML per call
    was one of the most expensive ops in the pipeline)."""
    global _HAAR_DETECTOR, _HAAR_TRIED
    if not _HAAR_TRIED:
        _HAAR_TRIED = True
        path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        if os.path.exists(path):
            _HAAR_DETECTOR = cv2.CascadeClassifier(path)
    return _HAAR_DETECTOR


def detect_faces(image_bgr: np.ndarray, min_size_ratio: float = 0.04,
                 detector=None) -> list[tuple[int, int, int, int]]:
    """Return list of (x, y, w, h) face bounding boxes (full-res coords)."""
    detector = detector if detector is not None else _haar_face_detector()
    if detector is None:
        return []
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]

    # Detect on a downscaled copy; scale boxes back up
    scale = 1.0
    if max(h, w) > _DETECT_MAX_EDGE:
        scale = _DETECT_MAX_EDGE / max(h, w)
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)),
                          interpolation=cv2.INTER_AREA)

    gh, gw = gray.shape[:2]
    min_size = int(min(gh, gw) * min_size_ratio)
    faces = detector.detectMultiScale(
        gray,
        scaleFactor=1.15,
        minNeighbors=4,
        minSize=(max(24, min_size), max(24, min_size)),
    )
    inv = 1.0 / scale
    return [tuple(int(round(v * inv)) for v in face) for face in faces]


# ── Character record ────────────────────────────────────────────────────────


@dataclass
class Character:
    """Tracked character — accumulated across pages."""

    cid: int
    embedding: np.ndarray  # CLIP feature, may be None
    skin_lab: np.ndarray  # mean LAB for skin region (3 floats)
    clothes_lab: np.ndarray  # mean LAB for clothes region (3 floats)
    n_observations: int = 1
    last_seen_page: int = 0


# ── Manager ─────────────────────────────────────────────────────────────────


class CharacterMemory:
    """Cluster faces into characters and provide per-character chroma transfer."""

    def __init__(self, similarity_threshold: float = 0.88):
        self._chars: list[Character] = []
        self._next_cid = 0
        self._sim_thr = similarity_threshold
        # CLIP loads lazily on the first embed — constructing a
        # CharacterMemory must not pull a vision model onto the GPU
        self._clip_model = None
        self._clip_proc = None
        self._clip_tried = False
        self._haar = _haar_face_detector()

    @property
    def enabled(self) -> bool:
        """True if face detection is available (CLIP is optional)."""
        return self._haar is not None

    @property
    def has_clip(self) -> bool:
        self._ensure_clip()
        return self._clip_model is not None

    def _ensure_clip(self):
        if not self._clip_tried:
            self._clip_tried = True
            self._clip_model, self._clip_proc = _try_load_clip()

    # ── Embedding ───────────────────────────────────────────────────────────

    def _embed(self, face_bgr: np.ndarray) -> np.ndarray | None:
        """Return a 1D CLIP embedding for a face crop, or None on any failure."""
        self._ensure_clip()
        if self._clip_model is None or self._clip_proc is None:
            return None
        try:
            import torch
            if face_bgr.size == 0:
                return None
            rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
            inputs = self._clip_proc(images=rgb, return_tensors="pt")
            inputs = {k: v.to(_CLIP_DEVICE) for k, v in inputs.items()}
            with torch.inference_mode():
                out = self._clip_model(**inputs)
            # CLIPVisionModelWithProjection returns (image_embeds, last_hidden_state, ...)
            feats = getattr(out, "image_embeds", None)
            if feats is None:
                return None
            v = feats[0].detach().float().cpu().numpy().reshape(-1)
            if v.ndim != 1 or v.size == 0:
                return None
            n = float(np.linalg.norm(v)) + 1e-8
            return (v / n).astype(np.float32)
        except Exception as exc:
            print(f"[character_memory] embed failed: {exc}")
            return None

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        if a is None or b is None:
            return -1.0
        if a.ndim != 1 or b.ndim != 1 or a.shape != b.shape:
            return -1.0
        return float(np.dot(a, b))

    # ── Color signature extraction ──────────────────────────────────────────

    @staticmethod
    def _skin_lab(face_bgr: np.ndarray) -> np.ndarray:
        """Mean LAB of likely-skin pixels in a face crop."""
        if face_bgr.size == 0:
            return np.array([128.0, 128.0, 128.0], dtype=np.float32)
        ycrcb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2YCrCb)
        cr = ycrcb[:, :, 1]
        cb = ycrcb[:, :, 2]
        # Loose skin detector in YCrCb
        mask = (cr >= 135) & (cr <= 180) & (cb >= 85) & (cb <= 135)
        if mask.sum() < 25:
            mask = np.ones_like(cr, dtype=bool)
        lab = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
        return np.array([
            float(np.mean(lab[mask, 0])),
            float(np.mean(lab[mask, 1])),
            float(np.mean(lab[mask, 2])),
        ], dtype=np.float32)

    @staticmethod
    def _clothes_lab(image_bgr: np.ndarray, face_box: tuple[int, int, int, int]) -> np.ndarray:
        """Sample the region just below the face as a proxy for clothing colors."""
        x, y, w, h = face_box
        H, W = image_bgr.shape[:2]
        y1 = min(H, y + h)
        y2 = min(H, y + h + int(h * 1.5))
        x1 = max(0, x - int(w * 0.25))
        x2 = min(W, x + w + int(w * 0.25))
        if y2 <= y1 or x2 <= x1:
            return np.array([128.0, 128.0, 128.0], dtype=np.float32)
        crop = image_bgr[y1:y2, x1:x2]
        if crop.size == 0:
            return np.array([128.0, 128.0, 128.0], dtype=np.float32)
        lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        mask = (gray > 30) & (gray < 240)
        if mask.sum() < 25:
            mask = np.ones_like(gray, dtype=bool)
        return np.array([
            float(np.mean(lab[mask, 0])),
            float(np.mean(lab[mask, 1])),
            float(np.mean(lab[mask, 2])),
        ], dtype=np.float32)

    # ── Public API ──────────────────────────────────────────────────────────

    def analyze(self, image_bgr: np.ndarray) -> list[dict]:
        """Detect faces once and compute the expensive per-face features.

        Returns a list of ``{"box", "emb", "skin"}`` dicts that can be passed
        to both :meth:`apply` and :meth:`observe` so detection + CLIP
        embedding run exactly once per page instead of twice.
        """
        if not self.enabled:
            return []
        try:
            faces = detect_faces(image_bgr, detector=self._haar)
        except Exception as exc:
            print(f"[character_memory] face detect failed: {exc}")
            return []

        detections: list[dict] = []
        for box in faces:
            try:
                x, y, w, h = box
                face_crop = image_bgr[y:y + h, x:x + w]
                detections.append({
                    "box": box,
                    "emb": self._embed(face_crop),
                    "skin": self._skin_lab(face_crop),
                })
            except Exception as exc:
                print(f"[character_memory] analyze-face skipped: {exc}")
                continue
        return detections

    def observe(self, image_bgr: np.ndarray, page_num: int = 0,
                detections: list[dict] | None = None) -> list[tuple[Character, tuple[int, int, int, int]]]:
        """Update the character registry from faces on *image_bgr*.

        Pass ``detections`` from :meth:`analyze` to reuse boxes and CLIP
        embeddings; skin/clothes signatures are re-sampled from the (possibly
        re-toned) image so the registry tracks the final output colors.
        Any per-face failure is logged and skipped — never raised.
        """
        if not self.enabled:
            return []
        if detections is None:
            detections = self.analyze(image_bgr)

        out: list[tuple[Character, tuple[int, int, int, int]]] = []
        for det in detections:
            try:
                box = det["box"]
                x, y, w, h = box
                face_crop = image_bgr[y:y + h, x:x + w]
                skin = self._skin_lab(face_crop)
                clothes = self._clothes_lab(image_bgr, box)
                char = self._match_or_create(det["emb"], skin, clothes, page_num)
                out.append((char, box))
            except Exception as exc:
                print(f"[character_memory] observe-face skipped: {exc}")
                continue
        return out

    def _match_or_create(self, emb: np.ndarray | None,
                         skin: np.ndarray, clothes: np.ndarray,
                         page_num: int) -> Character:
        """Match to an existing character or register a new one."""
        if emb is not None:
            best = (-1, -1.0)
            for i, c in enumerate(self._chars):
                if c.embedding is None:
                    continue
                sim = self._cosine(emb, c.embedding)
                if sim > best[1]:
                    best = (i, sim)
            if best[0] >= 0 and best[1] >= self._sim_thr:
                return self._update(self._chars[best[0]], emb, skin, clothes, page_num)
        else:
            # No CLIP — fall back to LAB skin distance
            best = (-1, 1e9)
            for i, c in enumerate(self._chars):
                d = float(np.linalg.norm(skin - c.skin_lab))
                if d < best[1]:
                    best = (i, d)
            if best[0] >= 0 and best[1] < 18.0:
                return self._update(self._chars[best[0]], emb, skin, clothes, page_num)

        char = Character(
            cid=self._next_cid,
            embedding=emb,
            skin_lab=skin.copy(),
            clothes_lab=clothes.copy(),
            last_seen_page=page_num,
        )
        self._next_cid += 1
        self._chars.append(char)
        return char

    @staticmethod
    def _update(char: Character, emb: np.ndarray | None,
                skin: np.ndarray, clothes: np.ndarray,
                page_num: int) -> Character:
        """Running average update of a character's signature."""
        n = char.n_observations
        weight = 1.0 / (n + 1)
        char.skin_lab = char.skin_lab * (1.0 - weight) + skin * weight
        char.clothes_lab = char.clothes_lab * (1.0 - weight) + clothes * weight
        if emb is not None:
            if char.embedding is not None:
                avg = char.embedding * (1.0 - weight) + emb * weight
                avg /= (np.linalg.norm(avg) + 1e-8)
                char.embedding = avg.astype(np.float32)
            else:
                char.embedding = emb
        char.n_observations += 1
        char.last_seen_page = page_num
        return char

    def apply(self, image_bgr: np.ndarray, page_num: int,
              strength: float = 0.6,
              detections: list[dict] | None = None) -> np.ndarray:
        """Re-tone faces/clothes on *image_bgr* toward stored character palettes.

        Used on pages 2+ to keep characters' skin & clothes consistent with
        their first colored appearance.  Pass ``detections`` from
        :meth:`analyze` to skip re-detecting and re-embedding.  Any failure
        returns the image untouched rather than raising.
        """
        if not self.enabled or not self._chars:
            return image_bgr

        if detections is None:
            detections = self.analyze(image_bgr)
        if not detections:
            return image_bgr

        out = image_bgr.copy()
        H, W = out.shape[:2]
        for det in detections:
            try:
                box = det["box"]
                x, y, w, h = box
                emb = det["emb"]
                skin = det["skin"]

                best = None
                best_score = -1.0
                for c in self._chars:
                    if emb is not None and c.embedding is not None:
                        score = self._cosine(emb, c.embedding)
                    else:
                        score = -float(np.linalg.norm(skin - c.skin_lab)) / 18.0 + 1.0
                    if score > best_score:
                        best_score = score
                        best = c

                if best is None or best_score < 0.5:
                    continue

                self._blend_region(out, box, best.skin_lab, strength)

                cy1 = min(H, y + h)
                cy2 = min(H, y + h + int(h * 1.5))
                cx1 = max(0, x - int(w * 0.25))
                cx2 = min(W, x + w + int(w * 0.25))
                if cy2 > cy1 and cx2 > cx1:
                    self._blend_region(out, (cx1, cy1, cx2 - cx1, cy2 - cy1),
                                       best.clothes_lab, strength * 0.7)
            except Exception as exc:
                print(f"[character_memory] apply-face skipped: {exc}")
                continue
        return out

    @staticmethod
    def _blend_region(image_bgr: np.ndarray, box: tuple[int, int, int, int],
                      target_lab: np.ndarray, strength: float) -> None:
        """In-place LAB chrominance blend toward *target_lab* inside *box*."""
        x, y, w, h = box
        x2, y2 = x + w, y + h
        H, W = image_bgr.shape[:2]
        x = max(0, x); y = max(0, y); x2 = min(W, x2); y2 = min(H, y2)
        if x2 <= x or y2 <= y:
            return
        crop = image_bgr[y:y2, x:x2]
        lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
        # Soft elliptical mask centered on the box
        ch, cw = lab.shape[:2]
        yy, xx = np.ogrid[:ch, :cw]
        cy, cx = ch / 2.0, cw / 2.0
        rad2 = ((xx - cx) / max(cw, 1)) ** 2 + ((yy - cy) / max(ch, 1)) ** 2
        soft = np.clip(1.0 - rad2 * 4.0, 0.0, 1.0).astype(np.float32)
        soft *= strength
        # Shift the region's MEAN chroma toward the target instead of
        # blending every pixel toward a constant — preserves the shading
        # variation inside the region (constant-blend stamped flat
        # airbrushed patches onto faces/clothes)
        w = soft / max(float(soft.sum()), 1.0)
        region_mean_a = float((lab[:, :, 1] * w).sum())
        region_mean_b = float((lab[:, :, 2] * w).sum())
        lab[:, :, 1] += (float(target_lab[1]) - region_mean_a) * soft
        lab[:, :, 2] += (float(target_lab[2]) - region_mean_b) * soft
        np.clip(lab, 0, 255, out=lab)
        image_bgr[y:y2, x:x2] = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR)

    def summary(self) -> list[dict]:
        """Return a JSON-friendly snapshot of tracked characters."""
        return [
            {
                "cid": c.cid,
                "n_observations": c.n_observations,
                "last_seen_page": c.last_seen_page,
                "skin_lab": [float(v) for v in c.skin_lab],
                "clothes_lab": [float(v) for v in c.clothes_lab],
                "has_embedding": c.embedding is not None,
            }
            for c in self._chars
        ]
