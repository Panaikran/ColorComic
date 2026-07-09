# v0.6.0 CUDA Device Audit

This audit records current device and CUDA selection paths before any CUDA
preview wiring. It does not enable CUDA or change runtime behavior.

## Current Central Helper

`core/device_detection.py` is the only centralized helper today.

- `detect_device_capabilities()` reports CPU availability, CUDA availability,
  CUDA version, GPU names, VRAM, Torch version, and CUDA query errors without
  loading models.
- `resolve_compute_device()` resolves `cpu`, `auto`, and `cuda`.
- With `official_cpu_build=True`, every request resolves to CPU.
- With `official_cpu_build=False`, `auto` still resolves to CPU, while explicit
  `cuda` resolves to CUDA only when CUDA is available.

No model-loading path currently calls `resolve_compute_device()`.

## Device Selection Call Sites

### `config.py`

- `Config.ML_DEVICE` is read from `COLORCOMIC_DEVICE`, defaulting to `auto`.
- This is the source value passed into model manager and optional upscaler
  construction.

### `app.py`

- `get_model_manager()` creates `ModelManager(device=Config.ML_DEVICE)`.
- `get_post_processor()` passes `Config.ML_DEVICE` into `Upscaler` when
  optional ESRGAN upscaling is enabled.
- `_run_colorization_job()` calls `model_manager.switch_device(job.device)`
  before loading the colorizer.
- `_probe_device_summary()` imports Torch directly and reports:
  - `cuda` when `Config.ML_DEVICE == "auto"` and `torch.cuda.is_available()`
  - otherwise `Config.ML_DEVICE`
- `/api/gpu-info` imports Torch directly, calls `torch.cuda.*`, and recommends
  CUDA when the first GPU reports at least 2 GB VRAM.

### `core/model_manager.py`

- `cuda_available` directly returns `torch.cuda.is_available()`.
- `_resolve_device()` directly returns `torch.device("cuda")` for `auto` when
  CUDA is available, otherwise CPU.
- `switch_device()` stores the requested string and reloads any active model.
- `_load_mcv2()` passes the raw stored device string into `MangaColorizer`.
- `_load_manganinja()` passes the raw stored device string into
  `MangaNinjaColorizer`.
- `_flush_vram()` directly calls `torch.cuda.empty_cache()` when CUDA is
  available.

### `core/ml_colorizer.py`

- `_resolve_device()` directly chooses CUDA for `auto` when
  `torch.cuda.is_available()`.
- Explicit device strings are passed directly to `torch.device()`.
- Auto mode has one CUDA fallback: if colorization raises a `RuntimeError`
  containing `out of memory` and the current device is not CPU, it clears CUDA
  cache, reloads the model on CPU, and retries the page.
- `unload()` clears CUDA cache when CUDA is available.

### `core/manga_ninja_colorizer.py`

- `_resolve_device()` directly chooses CUDA for `auto` when
  `torch.cuda.is_available()`.
- Explicit device strings are passed directly to `torch.device()`.
- CUDA mode uses `torch.float16`; CPU mode uses `torch.float32`.
- Reference mode does not currently retry on CPU after CUDA OOM or CUDA runtime
  failure.
- `unload()` clears CUDA cache when CUDA is available.

### `core/upscaler.py`

- `_resolve_device()` directly chooses CUDA for `auto` when
  `torch.cuda.is_available()`.
- Optional ESRGAN upscaling uses half precision on CUDA.
- It does not currently use `resolve_compute_device()`.

## Current CPU Fallback Behavior

Auto mode:

- Source/runtime `auto` can select CUDA when a CUDA-capable Torch build reports
  CUDA available.
- If a CUDA page colorization call raises an OOM `RuntimeError`, Auto mode
  reloads the Auto colorizer on CPU and retries that page.
- Non-OOM CUDA errors are re-raised.

Reference mode:

- Source/runtime `auto` can select CUDA when a CUDA-capable Torch build reports
  CUDA available.
- CUDA uses float16 for the pipeline.
- There is no explicit CPU retry for CUDA OOM or partial pipeline-load failure.
- Failures flow through the existing colorization error path.

Optional ESRGAN upscaler:

- Source/runtime `auto` can select CUDA when a CUDA-capable Torch build reports
  CUDA available.
- There is no explicit CPU retry on CUDA OOM.

## CPU-Only Packaging Assumptions

- `requirements-windows-cpu.txt` pins `torch==2.3.1+cpu` and
  `torchvision==0.18.1+cpu`.
- `requirements-windows-cuda-experimental.txt` exists for source-only developer
  CUDA experiments and is not used by the official build scripts.
- `packaging/ColorComic.spec` is named and documented as the CPU desktop spec.
- `packaging/build_windows.ps1` builds only `packaging\ColorComic.spec`.
- `packaging/build_installer.ps1` expects
  `ColorComic-Setup-0.5.0-win64-cpu.exe`.
- `packaging/inno/ColorComic.iss` emits `ColorComic-Setup-{version}-win64-cpu`.
- `packaging/README.md` and `packaging/CUDA_BUILD_PLAN.md` keep the official
  installer CPU-only and recommend a separate CUDA preview installer if CUDA
  ships later.

The official CPU build is CPU-only because of its dependency file and packaging
pipeline, not because runtime model-loading paths consult
`resolve_compute_device()`.

## Bypass Summary

Already centralized:

- `core/device_detection.py`
- `tests/test_device_detection.py`

Bypasses centralized resolution:

- `app.py` `_probe_device_summary()`
- `app.py` `/api/gpu-info`
- `core/model_manager.py`
- `core/ml_colorizer.py`
- `core/manga_ninja_colorizer.py`
- `core/upscaler.py`

## Phase 2 Wiring Order

1. Add a minimal preview-build switch, defaulting to official CPU behavior.
   Keep the default `official_cpu_build=True`.
2. Route `app.py` device status through `detect_device_capabilities()` and
   `resolve_compute_device()` so diagnostics/status match the same rules as
   model loading.
3. Route `ModelManager._resolve_device()` and `cuda_available` through the
   centralized helper.
4. Pass resolved device decisions from `ModelManager` into `MangaColorizer` and
   `MangaNinjaColorizer` without exposing CUDA in Preferences yet.
5. Update `MangaColorizer._resolve_device()` to use the same helper and preserve
   its current Auto-mode OOM fallback.
6. Update `MangaNinjaColorizer._resolve_device()` after Auto mode is covered,
   because Reference mode has heavier VRAM and no CPU retry today.
7. Update `Upscaler._resolve_device()` last, because it is optional and only
   active when ESRGAN is enabled.
8. Add mocked tests proving:
   - official CPU builds never resolve CUDA
   - CUDA preview builds can resolve explicit CUDA
   - CUDA unavailable falls back to CPU
   - current CPU Preferences behavior remains unchanged

## Risks

- Runtime source mode can currently select CUDA directly when `auto` is used
  with a CUDA Torch build, even though the official installer is CPU-only.
- Reference mode CUDA failures are riskier than Auto mode because a partial SD
  1.5/MangaNinja pipeline load may consume significant VRAM before failing.
- `/api/gpu-info` still uses a 2 GB CUDA recommendation that is lower than the
  v0.5.0 CUDA planning guidance for Auto mode.
- Optional ESRGAN upscaling has its own direct CUDA path and no OOM retry.
- Packaging must stay separate; a unified installer would increase size and
  risk for CPU users.
