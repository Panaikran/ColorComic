# ColorComic

Colorize black-and-white comic and manga pages with deep learning — and make them
look **hand-colored, not washed over**. Upload a PDF, get back a fully colorized
version where skin, hair, clothes, and backgrounds each get their own color.
Auto and reference modes run entirely on your machine; an optional text-only LLM
can direct the palette.

![Version](https://img.shields.io/badge/version-2.0.0-blue)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![PyTorch](https://img.shields.io/badge/PyTorch-2.3%2B-ee4c2c)
![Flask](https://img.shields.io/badge/Flask-3.0%2B-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)

> **What's new in 2.0** — a guided-coloring pipeline that segments each page,
> identifies regions with a local vision model, and hints the colorizer with a
> real palette so pages read like finished manhwa instead of a single tinted
> wash. Plus a ~2–3× faster reference mode, retuned color-realism defaults, and a
> reworked UI. See [`CHANGELOG.md`](CHANGELOG.md).

## Features

- **Three colorization modes**
  - **Auto** — fully automatic, no reference needed (manga-colorization-v2), now
    with **guided coloring** for distinct per-object colors.
  - **Reference** — upload one colored page for higher-fidelity results
    (MangaNinja, CVPR 2025).
  - **LLM** — use an OpenRouter image-generation model with your API key.
- **Guided coloring (auto mode)** — segment page → identify regions with local
  CLIP → assign a palette → hint the model. Distinct colors per object, by design.
- **AI color director (optional, text-only)** — a chat LLM (e.g. DeepSeek) reads a
  *text* summary of the book and picks the palette. It never sees or generates
  images — it directs; the local model paints. Toggleable per job; off by default.
- **Tuned for realism & the manhwa look** — flat cel fills, natural skin tones, a
  fade floor that keeps bright surfaces colored, and a monochrome-wash detector
  that flags pages worth re-rolling.
- **Style & quality presets** — Shonen, Seinen, Webtoon, **Manhwa Flat Color**,
  Watercolor, Marvel/DC, 90s Pulp, Neutral × Draft / Standard / Ultra.
- **Post-processing pipeline** — L-channel preservation for line fidelity, guided
  filter for clean edges, cel flattening, skin-tone correction.
- **Optional 4× upscaling** — built-in Real-ESRGAN for print-quality output.
- **VRAM-aware model management** — one colorizer on the GPU at a time; evicted
  models are parked on CPU RAM so switching back is fast. Safe for 8 GB GPUs.
- **Live preview & editing** — real-time progress, A/B slider, per-page re-roll,
  paint-bucket touch-up with undo, per-page CMYK export.
- **PDF in, PDF out**, with automatic weight downloads on first use.

## How It Works

### Auto Mode (guided coloring + post-processing)

```
Upload PDF → extract pages (300 DPI, background thread)
  → Build the book's color script once:
      segment anchor page into regions → CLIP labels them
      → color director picks a palette (static, or text-only LLM)
  → For each page:
      segment + label regions → place palette color hints
      → mc-v2 colorize with hints (guided)
      → post-process: L-channel · masks · cel-flatten · guided filter
                      · vibrance · skin-tone correction
      → cross-page color consistency (LAB transfer, pages 2+)
      → [Ultra] Real-ESRGAN 4× upscale (last)
  → reassemble PDF → preview / download
```

Auto mode uses [manga-colorization-v2](https://github.com/qweasdd/manga-colorization-v2),
a U-Net with an SEResNeXt encoder. Its normally-unused *hint channel* is now fed
sparse color dots derived from segmentation + CLIP labels + the color script, so
it propagates chosen colors with its own learned shading rather than inventing a
global cast.

### Reference Mode (MangaNinja)

```
Upload PDF + reference image(s) → extract pages
  → For each page:
      MangaNinja colorize (reference attention, DPM-Solver++ ~16 steps)
      → post-processing
  → reassemble PDF → preview / download
```

Reference mode uses [MangaNinja](https://github.com/ali-vilab/MangaNinjia)
(CVPR 2025): it transfers a colored reference page's palette to every target page
via a dual-UNet architecture with reference attention. The reference's encodings
are computed once and reused across all pages.

### LLM Mode (OpenRouter image model)

```
Upload PDF → extract pages
  → For each page: send image to an OpenRouter image model → receive colorized page
  → post-processing → reassemble PDF
```

Set `OPENROUTER_API_KEY`, then choose **LLM (OpenRouter)** on the upload page.
Default model is `google/gemini-2.5-flash-image` (`OPENROUTER_MODEL`).

## The color director (text-only LLM)

Guided coloring works fully offline with a curated static palette. If you set an
OpenRouter key and enable the director, one small **text-only** request per book
lets a chat model choose the palette from a summary like
`{"region_counts": {"skin": 9, "hair": 7, "clothing": 12, ...}}`. It returns hex
colors and a mood; **no images are ever sent or generated**.

- Off by default in the shipped config (`LLM_DIRECTOR=0`) so a public deployment
  never spends credits silently.
- Toggle per job with the **AI color director** checkbox on the upload page.
- Point `OPENROUTER_DIRECTOR_MODEL` at any text model on
  [openrouter.ai/models](https://openrouter.ai/models) (e.g. a DeepSeek model).

## Requirements

- **Python** 3.10+
- **PyTorch** 2.3+ (with CUDA for GPU acceleration)
- **~140 MB download** for auto-mode weights (auto-downloaded)
- **~600 MB download** for the CLIP region classifier on first guided run
- **~6 GB download** for reference-mode weights (on first reference use)
- **GPU (optional):** any NVIDIA GPU with 2+ GB VRAM for auto mode, 6+ GB for
  reference mode. CPU works but is much slower.

### VRAM & speed (GPU)

| Mode | VRAM | Speed |
|------|------|-------|
| Auto (mc-v2) | ~3 GB | ~2–4 s/page |
| Auto + guided coloring | ~4 GB | +~1 s/page (CLIP) |
| Auto + ESRGAN (Ultra) | ~4 GB | ~6–10 s/page |
| Reference (MangaNinja) | ~6 GB | ~8–15 s/page |

Only one colorizer is on the GPU at a time; switching modes parks the previous one
on CPU RAM (fast to revive) rather than reloading from disk.

## Installation

### 1. Clone

```bash
git clone https://github.com/vikast908/ColorComic.git
cd ColorComic
```

### 2. Virtual environment

```bash
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
```

### 3. Install PyTorch

**With GPU (NVIDIA CUDA):** pick your CUDA version at
[pytorch.org/get-started](https://pytorch.org/get-started/locally/), or:

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128  # CUDA 12.8
```

**CPU only:**

```bash
pip install torch torchvision
```

### 4. Remaining dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure (optional)

```bash
cp .env.example .env
```

Edit `.env` to change defaults or add your OpenRouter key. See
[Configuration](#configuration) for every option.

### 6. Run

```bash
python app.py
```

Open **http://127.0.0.1:5000**. Weights download automatically on first use.

## Usage

1. **Upload** a B&W comic/manga PDF.
2. **Choose a mode** — Auto, Reference (+ a colored reference image), or LLM.
3. **Pick a style + quality** — e.g. *Manhwa Flat Color* + *Standard*.
4. *(Auto mode)* optionally toggle the **AI color director**.
5. **Detect GPU** if you want to review hardware, then colorize.
6. **Review & edit** — flip pages, compare with the A/B slider, re-roll weak pages
   (the quality badge flags monochrome-wash pages), touch up regions, then download.

## Configuration

All settings are environment variables (see `.env.example`).

| Variable | Default | Description |
|---|---|---|
| `COLORCOMIC_DEVICE` | `auto` | Inference device. `auto` picks GPU if available. |
| `COLOR_TRANSFER_STRENGTH` | `0.5` | Cross-page color alignment strength (0–1). Auto mode. |
| `POSTPROCESS_L_CHANNEL` | `1` | Preserve original luminance for sharp lines. |
| `POSTPROCESS_GUIDED_FILTER` | `1` | Smooth color bleeding at edges. |
| `POSTPROCESS_HARD_MASKS` | `1` | Force bubbles/gutters/ink neutral. |
| `SKIN_TONE_CORRECTION` | `1` | Nudge too-red skin toward the natural hue band. |
| `GUIDED_HINTS` | `1` | Segment + CLIP-label + hint the model (auto mode). |
| `LLM_DIRECTOR` | `0` | Let a text-only LLM pick the palette (needs API key). |
| `OPENROUTER_API_KEY` | empty | Required for LLM mode **and** the color director. |
| `OPENROUTER_DIRECTOR_MODEL` | `deepseek/deepseek-chat` | Text model for the color director. |
| `OPENROUTER_MODEL` | `google/gemini-2.5-flash-image` | Image model for LLM mode. |
| `OPENROUTER_MODALITIES` | `image,text` | Output modalities for LLM mode. |
| `OPENROUTER_MAX_INPUT_EDGE` | `1600` | Largest page edge sent to OpenRouter (LLM mode). |
| `MANGANINJA_DENOISE_STEPS` | `16` | Diffusion steps for reference mode (DPM-Solver++). |
| `DEHERRON_SCREENTONES` | `1` | Soften screentones before colorizing (auto mode). |
| `CHARACTER_MEMORY` | `1` | Per-character color memory across pages (auto mode). |
| `SD15_MODEL_PATH` / `CLIP_VISION_PATH` | HuggingFace | Reference-mode model overrides. |
| `SECRET_KEY` | random | Flask session secret. Set a fixed value in production. |

Style and quality presets (saturation, cel flattening, upscale, output format,
etc.) live in `core/presets.py` and are chosen per job in the UI.

## Project Structure

```
ColorComic/
├── app.py                       # Flask app, routes, per-job worker
├── config.py                    # Configuration + version
├── requirements.txt
├── CHANGELOG.md · CONTRIBUTING.md · LICENSE
│
├── core/
│   ├── model_manager.py         # VRAM-aware model switching (CPU parking)
│   ├── ml_colorizer.py          # mc-v2 wrapper + hint-channel rasterizer (auto)
│   ├── manga_ninja_colorizer.py # MangaNinja wrapper (reference)
│   ├── openrouter_colorizer.py  # OpenRouter image wrapper (LLM)
│   ├── guided_colorist.py       # Orchestrates segment → label → palette → hints
│   ├── region_segmenter.py      # Trapped-ball region segmentation
│   ├── region_classifier.py     # Local CLIP zero-shot region labels
│   ├── color_director.py        # Palette decision (static or text-only LLM)
│   ├── postprocessor.py         # Fused LAB pipeline (L-channel, masks, cel, etc.)
│   ├── masks.py                 # Bubble / lineart / gutter / screentone masks
│   ├── color_consistency.py     # Cross-page LAB color transfer
│   ├── character_memory.py      # Per-character color memory (auto)
│   ├── quality_score.py         # Per-page quality heuristics + wash detector
│   ├── paint_bucket.py          # Server-side flood-fill touch-up
│   ├── upscaler.py              # Real-ESRGAN 4× (self-contained, shared)
│   ├── output_writer.py         # JPEG/PNG/CMYK writers + preview derivatives
│   ├── reference_validator.py   # Pre-flight check for reference images
│   ├── cover_detector.py        # Palette-anchor page detection
│   ├── panel_detector.py        # Panel detection (per-panel colorizing)
│   ├── pdf_handler.py           # PDF extract / reassemble (PyMuPDF)
│   └── model_downloader.py      # Auto-download weights
│
├── models/
│   ├── schemas.py               # Pydantic models (JobState, PageQualityRecord…)
│   └── weights/                 # Auto-downloaded (gitignored)
│
├── vendor/
│   ├── manga_colorization_v2/   # Vendored mc-v2 inference code
│   └── manganinja/              # Vendored MangaNinja code (CC BY-NC 4.0)
│
├── templates/                   # base · index · processing · preview (Jinja2)
└── static/                      # css/style.css · js/upload.js
```

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Upload page |
| `POST` | `/upload` | Upload PDF (+ references, mode, style, quality, director toggle) |
| `POST` | `/api/validate-reference` | Pre-flight check for a reference image |
| `POST` | `/api/colorize/<job_id>` | Start colorization |
| `POST` | `/api/cancel/<job_id>` | Cancel a running job |
| `GET` | `/api/colorize/<job_id>/stream` | SSE stream of progress/stage events |
| `GET` | `/api/job/<job_id>` | Job status, per-page quality, versions |
| `GET` | `/api/preview/<job_id>/<page>?w=` | Colorized page (`w=` → downscaled) |
| `GET` | `/pages/<job_id>/<page>` | Original B&W page |
| `POST` | `/api/retry/<job_id>/<page>` | Re-roll one page (style/quality overrides) |
| `POST` | `/api/touchup/<job_id>/<page>` | Paint-bucket recolor at a point |
| `POST` | `/api/undo/<job_id>/<page>` | Undo the last edit on a page |
| `POST` | `/api/cmyk/<job_id>/<page>` | Export a page as CMYK TIFF |
| `GET` | `/api/download/<job_id>` | Download the colorized PDF |
| `GET` | `/api/download-cmyk/<job_id>/<page>` | Download a page's CMYK TIFF |
| `GET` | `/api/presets` | Available style/quality presets |
| `GET` | `/api/gpu-info` | GPU detection (name, VRAM, compute capability) |
| `GET` | `/api/status` | Health check (version, device, mode, CUDA) |

## Performance

- **Reference mode ~2.5–3× faster** — 2-way CFG when no point maps, DPM-Solver++
  at ~16 steps, and per-reference encoder caching.
- **Auto mode ~1.5–2× faster on GPU** — fp16 autocast; page denoised once.
- **Fused post-processing** — one grayscale + one LAB conversion shared across all
  chroma steps; upscale runs last so filters work at native resolution.
- **Model manager** parks evicted models on CPU RAM and compares resolved devices,
  eliminating spurious reloads and turning mode switches from minutes to seconds.
- **Shared Real-ESRGAN** with on-GPU tiling and uint8 readback; **background PDF
  extraction**; downscaled preview derivatives for the browser; and `inference_mode`
  + cuDNN autotuner throughout.

## Limitations

- **Manga/anime-optimized:** the local models are trained on manga art; Western
  comics may look weaker.
- **The base model is the ceiling:** guided coloring organizes and steers color but
  can't invent what the model won't paint. Reference or LLM mode give the most
  control for a specific palette.
- **Reference mode is CC BY-NC 4.0** (non-commercial) and needs a colored reference
  page; first use downloads ~6 GB of weights.
- **Single-user:** the Flask app uses in-memory job state with a TTL cleanup —
  designed for local/single-user use.

## Acknowledgments

- **[manga-colorization-v2](https://github.com/qweasdd/manga-colorization-v2)** by qweasdd — auto-mode model
- **[MangaNinja](https://github.com/ali-vilab/MangaNinjia)** by ali-vilab — reference model (CVPR 2025, CC BY-NC 4.0)
- **[Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN)** by xinntao — anime super-resolution
- **[CLIP](https://github.com/openai/CLIP)** by OpenAI — zero-shot region labeling
- **[FFDNet](https://github.com/cszn/FFDNet)** — denoising for preprocessing
- **[PyMuPDF](https://pymupdf.readthedocs.io/)** — PDF extraction and reassembly

## License

Project code is provided under the [MIT License](LICENSE).

Vendored manga-colorization-v2 and FFDNet code retain their original licenses.
Vendored MangaNinja code is [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)
(non-commercial only). See the respective repositories for details.
