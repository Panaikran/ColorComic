import os

from dotenv import load_dotenv

# Load .env BEFORE the Config class body reads os.environ — app.py's own
# load_dotenv() runs after this module is imported, which silently ignored
# every .env value consumed through Config.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Semantic version — bump on release and mirror in CHANGELOG.md
__version__ = "2.0.0"


class Config:
    VERSION = __version__
    SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(24).hex())
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    OUTPUT_FOLDER = os.path.join(BASE_DIR, "output")
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 200 MB

    # Image processing
    PAGE_DPI = 300
    PREVIEW_DPI = 150

    # ── manga-colorization-v2 (auto mode) ─────────────────────────────
    WEIGHTS_DIR = os.path.join(BASE_DIR, "models", "weights")
    GENERATOR_WEIGHTS_PATH = os.path.join(WEIGHTS_DIR, "generator.zip")
    EXTRACTOR_WEIGHTS_PATH = os.path.join(WEIGHTS_DIR, "extractor.pth")
    DENOISER_WEIGHTS_DIR = os.path.join(WEIGHTS_DIR, "denoiser")
    ML_DEVICE = os.environ.get("COLORCOMIC_DEVICE", "auto")
    # 0.5 keeps pages tonally coherent without forcing every scene into the
    # anchor page's palette (0.7 was a major cause of the single-wash look)
    COLOR_TRANSFER_STRENGTH = float(os.environ.get("COLOR_TRANSFER_STRENGTH", "0.5"))
    MCv2_SIZE = int(os.environ.get("MCV2_SIZE", "768"))
    MCv2_DENOISE_SIGMA = int(os.environ.get("MCV2_DENOISE_SIGMA", "15"))

    # ── MangaNinja (reference mode) ───────────────────────────────────
    MANGANINJA_WEIGHTS_DIR = os.path.join(WEIGHTS_DIR, "manganinja")
    MANGANINJA_DENOISING_UNET = os.path.join(MANGANINJA_WEIGHTS_DIR, "denoising_unet.pth")
    MANGANINJA_REFERENCE_UNET = os.path.join(MANGANINJA_WEIGHTS_DIR, "reference_unet.pth")
    MANGANINJA_POINTNET = os.path.join(MANGANINJA_WEIGHTS_DIR, "point_net.pth")
    MANGANINJA_CONTROLNET = os.path.join(MANGANINJA_WEIGHTS_DIR, "controlnet.pth")

    MANGANINJA_HF_REPO = "Johanan0528/MangaNinja"

    SD15_MODEL_PATH = os.environ.get(
        "SD15_MODEL_PATH", "stable-diffusion-v1-5/stable-diffusion-v1-5"
    )
    CLIP_VISION_PATH = os.environ.get(
        "CLIP_VISION_PATH", "openai/clip-vit-large-patch14"
    )
    CONTROLNET_LINEART_PATH = os.environ.get(
        "CONTROLNET_LINEART_PATH", "lllyasviel/control_v11p_sd15_lineart"
    )
    LINEART_ANNOTATOR_PATH = os.path.join(MANGANINJA_WEIGHTS_DIR, "annotators")

    # DPM-Solver++ scheduler reaches DDIM@30 quality in ~16 steps
    MANGANINJA_DENOISE_STEPS = int(os.environ.get("MANGANINJA_DENOISE_STEPS", "16"))

    # OpenRouter LLM/image mode
    OPENROUTER_API_URL = os.environ.get(
        "OPENROUTER_API_URL", "https://openrouter.ai/api/v1"
    )
    OPENROUTER_MODEL = os.environ.get(
        "OPENROUTER_MODEL", "google/gemini-2.5-flash-image"
    )
    OPENROUTER_SITE_URL = os.environ.get("OPENROUTER_SITE_URL", "")
    OPENROUTER_APP_NAME = os.environ.get("OPENROUTER_APP_NAME", "ColorComic")
    OPENROUTER_MODALITIES = [
        value.strip()
        for value in os.environ.get("OPENROUTER_MODALITIES", "image,text").split(",")
        if value.strip()
    ]
    OPENROUTER_TIMEOUT = int(os.environ.get("OPENROUTER_TIMEOUT", "300"))
    OPENROUTER_MAX_INPUT_EDGE = int(os.environ.get("OPENROUTER_MAX_INPUT_EDGE", "1600"))
    OPENROUTER_PROMPT = os.environ.get(
        "OPENROUTER_PROMPT",
        (
            "Colorize this black-and-white comic or manga page like a professionally "
            "colored manhwa/webtoon. Preserve the original line art, panel layout, "
            "speech bubbles, lettering, gutters, and composition. Use flat cel-style "
            "fills where every character, garment, object, and background element gets "
            "its own distinct, appropriate color — never tint the whole page with a "
            "single hue. Use natural skin tones. Keep text readable and avoid "
            "inventing new objects, changing poses, cropping, or redrawing the page."
        ),
    )

    # ── Real-ESRGAN upscaler ──────────────────────────────────────────
    ESRGAN_MODEL_PATH = os.path.join(WEIGHTS_DIR, "RealESRGAN_x4plus_anime_6B.pth")
    ESRGAN_MODEL_URL = (
        "https://github.com/xinntao/Real-ESRGAN/releases/download/"
        "v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth"
    )
    ESRGAN_SCALE = 4
    # 512 tiles = ~4x fewer kernel launches than 256; the fp16 6-block anime
    # model fits comfortably in 8 GB at this tile size
    ESRGAN_TILE = 512

    # ── Post-processing toggles (defaults — overridden by quality preset) ─
    POSTPROCESS_L_CHANNEL = os.environ.get("POSTPROCESS_L_CHANNEL", "1") == "1"
    POSTPROCESS_GUIDED_FILTER = os.environ.get("POSTPROCESS_GUIDED_FILTER", "1") == "1"
    POSTPROCESS_UPSCALE = os.environ.get("POSTPROCESS_UPSCALE", "0") == "1"
    POSTPROCESS_HARD_MASKS = os.environ.get("POSTPROCESS_HARD_MASKS", "1") == "1"

    # ── Color quality tuning (defaults — overridden by style preset) ────
    GUIDED_FILTER_RADIUS = int(os.environ.get("GUIDED_FILTER_RADIUS", "2"))
    GUIDED_FILTER_EPS = float(os.environ.get("GUIDED_FILTER_EPS", "0.01"))
    SATURATION_BOOST = float(os.environ.get("SATURATION_BOOST", "1.5"))
    NEUTRAL_PRESERVATION = os.environ.get("NEUTRAL_PRESERVATION", "1") == "1"
    JPEG_QUALITY = int(os.environ.get("JPEG_QUALITY", "92"))

    # ── Screentone pre-cleaning (auto mode only) ────────────────────────
    DEHERRON_SCREENTONES = os.environ.get("DEHERRON_SCREENTONES", "1") == "1"
    DEHERRON_STRENGTH = float(os.environ.get("DEHERRON_STRENGTH", "0.55"))

    # ── Skin-tone correction (post-processing) ──────────────────────────
    # Rotates too-red skin-like chroma toward the plausible 40-55 deg band
    SKIN_TONE_CORRECTION = os.environ.get("SKIN_TONE_CORRECTION", "1") == "1"

    # ── Guided coloring (auto mode) ─────────────────────────────────────
    # Segment page into lineart-bounded regions, label them with local
    # CLIP, and feed palette color hints into mc-v2's hint channel.
    GUIDED_HINTS = os.environ.get("GUIDED_HINTS", "1") == "1"
    # Text-only LLM refinement of the per-job color script (needs
    # OPENROUTER_API_KEY; the LLM guides — it never sees or makes images).
    # Default OFF so public deployments never spend API credits silently;
    # set LLM_DIRECTOR=1 in .env to default it on. The upload UI can
    # toggle it per job either way.
    LLM_DIRECTOR = os.environ.get("LLM_DIRECTOR", "0") == "1"
    # Set this to your preferred text model id from openrouter.ai/models
    # (e.g. the DeepSeek v4 flash id).
    OPENROUTER_DIRECTOR_MODEL = os.environ.get(
        "OPENROUTER_DIRECTOR_MODEL", "deepseek/deepseek-chat"
    )
    DIRECTOR_TIMEOUT = int(os.environ.get("DIRECTOR_TIMEOUT", "60"))
    GUIDED_CLIP_PATH = os.environ.get("GUIDED_CLIP_PATH", "openai/clip-vit-base-patch32")

    # ── Per-character memory ────────────────────────────────────────────
    CHARACTER_MEMORY = os.environ.get("CHARACTER_MEMORY", "1") == "1"
    CHARACTER_BLEND_STRENGTH = float(os.environ.get("CHARACTER_BLEND_STRENGTH", "0.55"))

    # ── Default presets (used if not specified in upload) ───────────────
    DEFAULT_STYLE = os.environ.get("DEFAULT_STYLE", "neutral")
    DEFAULT_QUALITY = os.environ.get("DEFAULT_QUALITY", "standard")
