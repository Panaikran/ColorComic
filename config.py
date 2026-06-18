import os

from core.paths import ensure_directories, get_app_base_dir, get_runtime_dir


BASE_DIR = get_app_base_dir()
RUNTIME_DIR = get_runtime_dir()
MODELS_DIR = os.path.join(RUNTIME_DIR, "models")
WEIGHTS_DIR = os.path.join(MODELS_DIR, "weights")
CACHE_DIR = os.path.join(RUNTIME_DIR, "cache")
HF_HOME = os.path.join(CACHE_DIR, "huggingface")
HF_HUB_CACHE = os.path.join(HF_HOME, "hub")
LOG_DIR = os.path.join(RUNTIME_DIR, "logs")
CONFIG_DIR = os.path.join(RUNTIME_DIR, "config")
CONFIG_FILE = os.path.join(CONFIG_DIR, ".env")

os.environ["HF_HOME"] = HF_HOME
os.environ["HF_HUB_CACHE"] = HF_HUB_CACHE
os.environ["HUGGINGFACE_HUB_CACHE"] = HF_HUB_CACHE
os.environ["TRANSFORMERS_CACHE"] = os.path.join(HF_HOME, "transformers")
os.environ["DIFFUSERS_CACHE"] = os.path.join(HF_HOME, "diffusers")

ensure_directories(
    RUNTIME_DIR,
    os.path.join(RUNTIME_DIR, "uploads"),
    os.path.join(RUNTIME_DIR, "output"),
    WEIGHTS_DIR,
    os.path.join(WEIGHTS_DIR, "manganinja"),
    HF_HOME,
    LOG_DIR,
    CONFIG_DIR,
)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(24).hex())
    BASE_DIR = BASE_DIR
    RUNTIME_DIR = RUNTIME_DIR
    CACHE_DIR = CACHE_DIR
    HF_HOME = HF_HOME
    HF_HUB_CACHE = HF_HUB_CACHE
    LOG_DIR = LOG_DIR
    CONFIG_DIR = CONFIG_DIR
    CONFIG_FILE = CONFIG_FILE
    UPLOAD_FOLDER = os.path.join(RUNTIME_DIR, "uploads")
    OUTPUT_FOLDER = os.path.join(RUNTIME_DIR, "output")
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 200 MB

    # Image processing
    PAGE_DPI = 300
    PREVIEW_DPI = 150

    # ── manga-colorization-v2 (auto mode) ─────────────────────────────
    WEIGHTS_DIR = WEIGHTS_DIR
    GENERATOR_WEIGHTS_PATH = os.path.join(WEIGHTS_DIR, "generator.zip")
    EXTRACTOR_WEIGHTS_PATH = os.path.join(WEIGHTS_DIR, "extractor.pth")
    DENOISER_WEIGHTS_DIR = os.path.join(WEIGHTS_DIR, "denoiser")
    ML_DEVICE = os.environ.get("COLORCOMIC_DEVICE", "auto")
    COLOR_TRANSFER_STRENGTH = float(os.environ.get("COLOR_TRANSFER_STRENGTH", "0.7"))

    # ── MangaNinja (reference mode) ───────────────────────────────────
    MANGANINJA_WEIGHTS_DIR = os.path.join(WEIGHTS_DIR, "manganinja")
    MANGANINJA_DENOISING_UNET = os.path.join(MANGANINJA_WEIGHTS_DIR, "denoising_unet.pth")
    MANGANINJA_REFERENCE_UNET = os.path.join(MANGANINJA_WEIGHTS_DIR, "reference_unet.pth")
    MANGANINJA_POINTNET = os.path.join(MANGANINJA_WEIGHTS_DIR, "point_net.pth")
    MANGANINJA_CONTROLNET = os.path.join(MANGANINJA_WEIGHTS_DIR, "controlnet.pth")

    MANGANINJA_HF_REPO = "Johanan0528/MangaNinjia"

    # Paths for SD 1.5 / CLIP / ControlNet base models (HuggingFace cache)
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

    MANGANINJA_DENOISE_STEPS = int(os.environ.get("MANGANINJA_DENOISE_STEPS", "30"))

    # ── Real-ESRGAN upscaler ──────────────────────────────────────────
    ESRGAN_MODEL_PATH = os.path.join(WEIGHTS_DIR, "RealESRGAN_x4plus_anime_6B.pth")
    ESRGAN_MODEL_URL = (
        "https://github.com/xinntao/Real-ESRGAN/releases/download/"
        "v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth"
    )
    ESRGAN_SCALE = 4
    ESRGAN_TILE = 256

    # ── Post-processing toggles ───────────────────────────────────────
    POSTPROCESS_L_CHANNEL = os.environ.get("POSTPROCESS_L_CHANNEL", "1") == "1"
    POSTPROCESS_GUIDED_FILTER = os.environ.get("POSTPROCESS_GUIDED_FILTER", "1") == "1"
    POSTPROCESS_UPSCALE = os.environ.get("POSTPROCESS_UPSCALE", "0") == "1"
