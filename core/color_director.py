"""Color director — decides the book's palette; a text LLM may refine it.

The director produces a "color script": one hex color per semantic
region class (skin, hair, metal, sky, …).  By default it's a curated
static palette.  When an OpenRouter key is configured, a TEXT-ONLY chat
model (e.g. DeepSeek) refines the script from a textual summary of what
was detected in the book — the LLM guides the system, it never sees or
generates pixels.

One director call per job (not per page): the palette must stay stable
across the whole book.
"""

import json
import os
import re

import requests


# Curated defaults — natural manhwa-leaning material colors (hex RGB).
DEFAULT_PALETTE: dict[str, str] = {
    "skin":               "#f0c8a0",
    "hair":               "#6b4a32",
    "clothing_primary":   "#5b7fa6",
    "clothing_secondary": "#a65e50",
    "clothing_accent":    "#c9a227",
    "metal":              "#9aa2ab",
    "wood":               "#8a6a48",
    "sky":                "#a5c6e8",
    "foliage":            "#6f9e5f",
    "stone":              "#8f8f92",
    "water":              "#6f9ec8",
    "fire":               "#e8862e",
    "background":         "#d9cfc0",
}

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

_SYSTEM_PROMPT = (
    "You are the color director for a manga/manhwa colorization pipeline. "
    "You are given a text summary of the regions detected across a black-and-white "
    "book (no images). Design ONE palette of hex colors that a professional "
    "colorist would choose for THIS specific book: natural skin, plausible "
    "materials, and clearly DISTINCT hues between classes so the result never "
    "looks like a single color wash. Tailor every color to the content summary "
    "and mood you infer from it — do not fall back on generic mid-tone choices. "
    "Respond with ONLY a JSON object of the form "
    '{"palette": {<key>: "#rrggbb", ...}, "mood": "<short description>"} '
    "containing exactly the keys you were given. No prose, no markdown fences."
)


def _valid_hex(value) -> bool:
    return isinstance(value, str) and bool(_HEX_RE.match(value.strip()))


def hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
    s = hex_color.lstrip("#")
    return int(s[4:6], 16), int(s[2:4], 16), int(s[0:2], 16)


class ColorDirector:
    """Builds the per-job color script (static, optionally LLM-refined)."""

    def __init__(self, config):
        self._cfg = config
        self._session = requests.Session()

    def build_script(self, tag_summary: dict, use_llm: bool | None = None) -> dict:
        """Return {"palette": {...}, "mood": str, "source": "static"|"llm"}.

        ``tag_summary`` is a small JSON-able description of the book —
        e.g. {"pages_sampled": 3, "region_counts": {"skin": 14, "sky": 2}}.
        ``use_llm`` overrides the configured LLM_DIRECTOR default (per-job
        UI toggle).  Never raises; always returns a usable script.
        """
        script = {"palette": dict(DEFAULT_PALETTE), "mood": "neutral daylight",
                  "source": "static"}

        if use_llm is None:
            use_llm = bool(getattr(self._cfg, "LLM_DIRECTOR", False))
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key or not use_llm:
            return script

        try:
            refined = self._ask_llm(api_key, tag_summary)
            if refined:
                palette = refined.get("palette") or {}
                accepted = {k: v.strip() for k, v in palette.items()
                            if k in DEFAULT_PALETTE and _valid_hex(v)}
                if accepted:
                    script["palette"].update(accepted)
                    script["source"] = "llm"
                if isinstance(refined.get("mood"), str):
                    script["mood"] = refined["mood"][:120]
                print(f"[color_director] LLM script accepted "
                      f"({len(accepted)}/{len(DEFAULT_PALETTE)} keys), "
                      f"mood: {script['mood']}")
        except Exception as exc:
            print(f"[color_director] LLM refinement skipped: {exc}")
        return script

    def _ask_llm(self, api_key: str, tag_summary: dict) -> dict | None:
        """One text-only chat completion. Returns parsed JSON or None."""
        # NOTE: deliberately no default palette in the payload — models
        # anchor on any example values and echo them back unchanged
        user_payload = {
            "detected_regions": tag_summary,
            "palette_keys_required": list(DEFAULT_PALETTE.keys()),
        }
        body = {
            "model": self._cfg.OPENROUTER_DIRECTOR_MODEL,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
            "temperature": 0.3,
            # Reasoning models burn tokens thinking BEFORE the answer — a
            # small cap can leave content empty (observed with DeepSeek)
            "max_tokens": 4000,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        resp = self._session.post(
            f"{self._cfg.OPENROUTER_API_URL.rstrip('/')}/chat/completions",
            headers=headers, json=body,
            timeout=getattr(self._cfg, "DIRECTOR_TIMEOUT", 60),
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"director request failed ({resp.status_code}): "
                               f"{resp.text[:200]}")

        choice = (resp.json().get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = msg.get("content")
        if isinstance(content, list):  # some providers return content parts
            content = "".join(p.get("text", "") for p in content
                              if isinstance(p, dict))
        if not content:
            # reasoning-only response — the answer sometimes hides there
            content = msg.get("reasoning") or ""
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(
                f"empty response (finish_reason={choice.get('finish_reason')})")

        # Models occasionally wrap JSON in fences or prose — extract the
        # outermost object.
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return None
        return json.loads(match.group(0))
