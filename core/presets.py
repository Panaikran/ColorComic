"""Style and quality presets.

Style presets bundle post-processing tunables (saturation curve, neutral
preservation, guided-filter sharpness) that match a target aesthetic.

Quality presets bundle resolution / tiling / output-format flags that
trade time for fidelity.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional


# ── Style presets ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StylePreset:
    """Bundle of post-processing knobs for a target aesthetic."""

    key: str
    label: str
    description: str
    # Saturation: peak multiplier for low-chroma pixels (vibrance).
    saturation_boost: float = 1.4
    # Neutral preservation thresholds.
    white_threshold: int = 220
    black_threshold: int = 30
    neutral_transition: int = 30
    # Chroma-aware L-blend: 0 = full original L (current behavior),
    # 1 = full colorized L. Used inside the line-mask falloff.
    l_blend_alpha: float = 0.0
    # Guided filter feel.
    guided_filter_radius: int = 2
    guided_filter_eps: float = 0.01
    # Optional global tone curve applied as gain on A/B chroma after sat boost.
    chroma_warm_shift: float = 0.0   # +shifts B channel (yellow), -shifts blue
    chroma_red_shift: float = 0.0    # +shifts A channel (red), -shifts green
    # Optional global luminance gamma (applied to L channel only outside ink).
    l_gamma: float = 1.0
    # Hint to the colorizer (denoise sigma / inference steps).
    denoise_sigma: int = 15
    diffusion_steps: int = 16
    # Cel flattening: snap each lineart-bounded region's chroma toward the
    # region mean (0 = off, 1 = fully flat fills).  This is what makes a page
    # read as hand-colored manhwa instead of one gradient wash.
    cel_flatten: float = 0.0
    # Floor for the soft neutral fade: bright surfaces (bedding, highlights,
    # light hair) always keep at least this fraction of their chroma.  Only
    # the hard masks (bubbles / gutters / ink) may force true zero.
    neutral_fade_floor: float = 0.35


STYLE_PRESETS: dict[str, StylePreset] = {
    "shonen": StylePreset(
        key="shonen",
        label="Shonen Vibrant",
        description="Punchy primaries, warm skin, high saturation — Jump-style.",
        saturation_boost=1.7,
        white_threshold=225,
        black_threshold=25,
        l_blend_alpha=0.15,
        guided_filter_radius=2,
        guided_filter_eps=0.012,
        chroma_warm_shift=4.0,
        chroma_red_shift=2.0,
        l_gamma=0.95,
        denoise_sigma=12,
        diffusion_steps=16,
    ),
    "seinen": StylePreset(
        key="seinen",
        label="Seinen Muted",
        description="Cool greys, restrained palette, cinematic shadows.",
        saturation_boost=1.15,
        white_threshold=215,
        black_threshold=35,
        l_blend_alpha=0.05,
        guided_filter_radius=3,
        guided_filter_eps=0.008,
        chroma_warm_shift=-2.0,
        l_gamma=1.05,
        denoise_sigma=18,
        diffusion_steps=18,
    ),
    "webtoon": StylePreset(
        key="webtoon",
        label="Webtoon",
        description="Flat cel-shaded, hard edges, bright clean colors.",
        saturation_boost=1.55,
        white_threshold=230,
        black_threshold=20,
        l_blend_alpha=0.20,
        guided_filter_radius=1,
        guided_filter_eps=0.02,
        chroma_warm_shift=2.0,
        l_gamma=0.98,
        denoise_sigma=10,
        diffusion_steps=14,
        cel_flatten=0.85,
    ),
    "manhwa": StylePreset(
        key="manhwa",
        label="Manhwa Flat Color",
        description="Distinct flat fills per region — the hand-colored manhwa look.",
        saturation_boost=1.45,
        white_threshold=238,
        black_threshold=25,
        neutral_transition=45,
        l_blend_alpha=0.18,
        guided_filter_radius=1,
        guided_filter_eps=0.02,
        l_gamma=0.98,
        denoise_sigma=12,
        diffusion_steps=16,
        cel_flatten=0.7,
    ),
    "watercolor": StylePreset(
        key="watercolor",
        label="Watercolor",
        description="Soft chroma falloff, gentle saturation, washed feel.",
        saturation_boost=1.10,
        white_threshold=210,
        black_threshold=40,
        neutral_transition=45,
        l_blend_alpha=0.10,
        guided_filter_radius=4,
        guided_filter_eps=0.005,
        chroma_warm_shift=1.0,
        l_gamma=1.02,
        denoise_sigma=20,
        diffusion_steps=16,
    ),
    "marvel": StylePreset(
        key="marvel",
        label="Marvel/DC",
        description="Saturated primaries, heavy shadow, comic-press feel.",
        saturation_boost=1.6,
        white_threshold=222,
        black_threshold=22,
        l_blend_alpha=0.12,
        guided_filter_radius=2,
        guided_filter_eps=0.014,
        chroma_warm_shift=3.0,
        chroma_red_shift=3.0,
        l_gamma=0.92,
        denoise_sigma=14,
        diffusion_steps=16,
    ),
    "pulp": StylePreset(
        key="pulp",
        label="90s Pulp",
        description="Limited palette, halftone-friendly, slightly faded.",
        saturation_boost=1.25,
        white_threshold=205,
        black_threshold=40,
        neutral_transition=40,
        l_blend_alpha=0.08,
        guided_filter_radius=3,
        guided_filter_eps=0.01,
        chroma_warm_shift=5.0,
        chroma_red_shift=1.5,
        l_gamma=1.08,
        denoise_sigma=22,
        diffusion_steps=14,
    ),
    "neutral": StylePreset(
        key="neutral",
        label="Neutral (default)",
        description="Faithful to model output, balanced post-processing.",
        saturation_boost=1.25,
        # Fade starts high so bright surfaces (bedding, highlights, light
        # hair) keep their color instead of collapsing to paper-white —
        # the old 220/30 stripped 50-84% of chroma above gray 190
        white_threshold=234,
        neutral_transition=42,
        l_blend_alpha=0.10,
        denoise_sigma=15,
        diffusion_steps=16,
        cel_flatten=0.35,
    ),
}


def get_style(key: Optional[str]) -> StylePreset:
    """Return a style preset by key, falling back to neutral."""
    if not key:
        return STYLE_PRESETS["neutral"]
    return STYLE_PRESETS.get(key.lower(), STYLE_PRESETS["neutral"])


# ── Quality presets ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class QualityPreset:
    """Bundle of resolution / tiling / output flags trading speed for fidelity."""

    key: str
    label: str
    description: str
    # Internal model resolution (mc-v2 working size, must be /32).
    model_size: int = 768
    # Tiled colorization at native page resolution.
    tiled_inference: bool = False
    tile_size: int = 768
    tile_overlap: int = 96
    # Per-panel colorization (uses panel_detector).
    per_panel: bool = False
    # Diffusion steps multiplier (applied to style preset's base).
    diffusion_step_mult: float = 1.0
    # Real-ESRGAN upscale.
    use_upscale: bool = False
    # Output format: "jpg" or "png".
    output_format: str = "jpg"
    jpeg_quality: int = 92
    # Multi-pass refinement (reference mode only).
    refine_pass: bool = False
    # Estimated seconds per page (rough hint for UI).
    seconds_per_page_estimate: float = 4.0


QUALITY_PRESETS: dict[str, QualityPreset] = {
    "draft": QualityPreset(
        key="draft",
        label="Draft",
        description="Fast preview — lower internal resolution, JPEG output.",
        model_size=576,
        tiled_inference=False,
        per_panel=False,
        diffusion_step_mult=0.7,
        use_upscale=False,
        output_format="jpg",
        jpeg_quality=85,
        seconds_per_page_estimate=2.0,
    ),
    "standard": QualityPreset(
        key="standard",
        label="Standard",
        description="Balanced — 768 internal, full post-processing.",
        model_size=768,
        tiled_inference=False,
        per_panel=True,
        diffusion_step_mult=1.0,
        use_upscale=False,
        output_format="jpg",
        jpeg_quality=95,
        seconds_per_page_estimate=5.0,
    ),
    "ultra": QualityPreset(
        key="ultra",
        label="Ultra",
        description="Tiled native resolution + per-panel + 4x upscale + refine pass.",
        model_size=768,
        tiled_inference=True,
        tile_size=768,
        tile_overlap=128,
        per_panel=True,
        diffusion_step_mult=1.3,
        use_upscale=True,
        # JPEG q95 4:4:4 — lossless PNG of continuous-tone colorized art is
        # 100-400 MB/page after 4x upscale and buys nothing visually
        output_format="jpg",
        jpeg_quality=95,
        refine_pass=True,
        seconds_per_page_estimate=30.0,
    ),
}


def get_quality(key: Optional[str]) -> QualityPreset:
    """Return a quality preset by key, falling back to standard."""
    if not key:
        return QUALITY_PRESETS["standard"]
    return QUALITY_PRESETS.get(key.lower(), QUALITY_PRESETS["standard"])


def all_styles_json() -> list[dict]:
    """Return all style presets in a UI-friendly form."""
    return [asdict(p) for p in STYLE_PRESETS.values()]


def all_qualities_json() -> list[dict]:
    """Return all quality presets in a UI-friendly form."""
    return [asdict(p) for p in QUALITY_PRESETS.values()]
