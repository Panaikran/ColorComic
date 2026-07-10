# Changelog

All notable changes to ColorComic are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] — 2026-07-10

A major overhaul focused on **color quality**, **raw performance**, and a
**guided-coloring** subsystem, plus a large UI/UX pass. The headline change is
that auto mode no longer paints a single tinted wash over the page — it now
colors distinct objects with distinct colors, the way a manhwa colorist would.

### Added

- **Guided coloring (auto mode).** A local "digital colorist" pipeline that runs
  before the model paints:
  - `core/region_segmenter.py` — trapped-ball-style segmentation splits each page
    into the lineart-bounded regions a colorist would flood-fill (ink dilation
    seals small gaps so color doesn't leak between regions).
  - `core/region_classifier.py` — local CLIP zero-shot labels each region
    (skin / hair / clothing / metal / wood / sky / foliage / stone / water /
    fire / background / bubble). No vision LLM.
  - `core/color_director.py` — decides the book's palette. Uses a curated static
    palette by default; when enabled, a **text-only** LLM (e.g. DeepSeek via
    OpenRouter) refines it from a *textual* summary of detected regions — the LLM
    directs, it never sees or generates pixels.
  - `core/guided_colorist.py` — turns regions + labels + palette into sparse
    color hints fed into manga-colorization-v2's (previously unused) native hint
    channel, so the model propagates *chosen* colors with its own learned shading.
- **AI color director toggle** — per-job checkbox on the upload page (auto mode
  only, disabled with a hint when no API key is set), backed by `LLM_DIRECTOR`.
  Defaults **off** in the shipped config so public deployments never spend API
  credits silently.
- **New "Manhwa Flat Color" style preset** — distinct flat cel fills per region.
- **Cel flattening** (`cel_flatten` preset field) — snaps each region's chroma
  toward its own mean for clean flat fills instead of gradient washes.
- **Skin-tone correction** — rotates too-red skin toward the natural CIELAB
  40–55° band (`SKIN_TONE_CORRECTION`).
- **`monochrome_wash` quality flag** — the per-page quality score now detects and
  flags pages where most colored pixels share a single hue, so the preview UI
  surfaces exactly which pages to re-roll.
- **Cancel a running job** — `POST /api/cancel/<job_id>` and a Cancel button on
  the processing page; the worker stops after the current page.
- **One-level undo for edits** — `POST /api/undo/<job_id>/<page>` plus an Undo
  button; touch-up and re-roll keep the previous image server-side.
- **Per-page CMYK download** — `GET /api/download-cmyk/<job_id>/<page>`.
- **Downscaled preview derivatives** — `GET /api/preview/...?w=720` serves a small
  JPEG for thumbnails/progress instead of multi-MB full-res pages.
- **Version endpoint** — `/api/status` now reports the app version.
- `CHANGELOG.md`, `CONTRIBUTING.md`, and expanded `.gitignore` / `.env.example`.

### Changed

- **Reference mode (MangaNinja) is ~2.5–3× faster** with no quality-relevant
  architecture change:
  - Dropped the dead third classifier-free-guidance branch (runs 2-way when no
    point maps are supplied — numerically identical).
  - Swapped DDIM@30 steps for DPM-Solver++ (Karras) at ~16 steps.
  - Caches the reference's CLIP / text / VAE encodings across all pages of a job.
  - Loads fine-tuned weights via `from_config` + `load_state_dict` instead of a
    redundant double `from_pretrained` of the SD 1.5 base.
- **Auto mode (mc-v2) is ~1.5–2× faster on GPU** via fp16 autocast; the FFDNet
  denoiser now runs once per page (not per tile/panel), without a single-GPU
  `DataParallel` wrapper.
- **Post-processing rewritten** — one shared grayscale + one float32 LAB
  conversion across all chroma steps (was ~10+ round-trips per page); hard masks
  and neutral fade fused into a single multiply.
- **Ultra preset no longer runs post-processing at 4× resolution** — the upscale
  moved to the *end* of the pipeline, cutting multi-GB transient allocations.
- **Model manager** compares *resolved* devices (so "auto" and "cuda" on the same
  box don't trigger a reload) and parks evicted models on CPU RAM instead of
  destroying them — mode switches are now seconds, not minutes.
- **Real-ESRGAN upscaler** is a shared singleton (no per-job/per-retry weight
  reloads), uses 512-px tiles, keeps the image on-GPU across tiles, and transfers
  results back as uint8.
- **Faster page prep** — PDF pages extracted in a background thread so `/upload`
  returns immediately; anchor detection reads 1/8-scale thumbnails.
- **Color-realism defaults retuned** — the "Neutral" preset no longer strips color
  from bright surfaces (`white_threshold` 220→234, `neutral_transition` 30→42),
  the vibrance curve now peaks at mid-chroma instead of amplifying near-neutral
  casts, and a fade floor keeps bright regions from washing out.
- **Cross-page color transfer** clamps its scale factors and defaults to strength
  0.5 (was 0.7) so one scene's palette isn't smeared onto every other page.
- **Standard/Ultra presets output high-quality JPEG** instead of lossless PNG
  (continuous-tone color art gains nothing from PNG at 10–100× the file size).
- **Processing page is resilient** — reconnecting SSE, monotonic progress driven
  by processed-page count, stage labels (extracting / loading model / assembling),
  and a correct done/error/cancelled state after refresh.
- **Preview page** gained keyboard navigation, click-to-zoom, a touch-capable A/B
  slider, per-page version cache-busting, and adjacent-page prefetch.
- **Upload page** now uses real XHR upload progress, per-reference validation
  badges, friendly error messages, and shows the GPU option up front when CUDA
  is present.
- Accessibility: focusable drop zones, `aria-live` status regions, visible
  focus styles, and semantic fieldsets.

### Fixed

- **Guided-hint background bug** — hint images use a mid-gray (128) background so
  the model's hint-channel normalization reads unhinted areas as neutral; a black
  background previously collapsed hinted pages to grayscale.
- **`.env` values consumed via `Config` were silently ignored** — `.env` is now
  loaded inside `config.py` before the class body reads it (previously loaded only
  after `Config` was imported).
- **CLIP loading** uses the `*WithProjection` model classes, fixing a crash on
  newer `transformers` where `get_text_features` no longer returns a bare tensor.
- **mc-v2 denoise ordering** — pages are resized to model size before denoising and
  the denoiser is fed the correct channel layout (fixes an "axes don't match
  array" crash).
- **16-bit input images** are downcast to 8-bit before channel fix-ups.
- Concurrency guard rejects a second colorize request for a job already running;
  finished jobs and their files are evicted after a TTL.
- Speech bubbles, gutters, and ink lines are reliably kept neutral; touch-up flood
  fill only recomputes its bounding-box region.

### Performance

- Fused LAB post-processing, vectorized bubble-mask (LUT instead of per-component
  scans), quality scoring on a ≤1024-px copy, cached Haar cascade with single
  downscaled face-detection pass, and root logging at INFO to keep third-party
  DEBUG spam out of the per-page hot path.

## [1.0.0] — 2026 (initial open-source release)

The baseline before the 2.0 overhaul — everything that was working up to this point.

### Added

- **Three colorization modes:** Auto (manga-colorization-v2), Reference
  (MangaNinja, CVPR 2025), and LLM (OpenRouter image models).
- **Post-processing pipeline** — L-channel preservation for line fidelity and a
  guided filter for clean edges.
- **Optional Real-ESRGAN 4× upscaling** for print-quality output.
- **VRAM-aware model management** — one colorizer loaded at a time, safe for 8 GB
  GPUs; automatic CPU fallback on out-of-memory.
- **Cross-page color consistency** via Reinhard LAB color transfer (auto mode).
- **GPU detection** — inspect hardware specs before choosing CPU or GPU.
- **Live preview** — side-by-side original vs. colorized during processing.
- **PDF in, PDF out** with automatic weight downloads on first use.
- Inference-pipeline optimizations: `torch.inference_mode`, cuDNN autotuner,
  GPU-resident tile accumulation, and MIT license for the project code.

[2.0.0]: https://github.com/vikast908/ColorComic/releases/tag/v2.0.0
[1.0.0]: https://github.com/vikast908/ColorComic/releases/tag/v1.0.0
