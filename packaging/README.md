# ColorComic Windows CPU Packaging

This folder contains the PyInstaller one-folder build setup for the CPU-only
desktop build. It uses `desktop.py` as the entrypoint and keeps model weights
out of the bundled application.

## Build Environment

Use a clean Windows virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-windows-cpu.txt
python -m pip install pyinstaller==6.10.0
```

Verify packaging-critical imports:

```powershell
python scripts\verify_dependency_imports.py
```

The official Windows installer is CPU-only. `requirements-windows-cuda-experimental.txt`
exists only for source-based developer CUDA experiments and is not used by
`build_windows.ps1`, `build_installer.ps1`, PyInstaller, or Inno Setup.
See `packaging\CUDA_BUILD_PLAN.md` for the future CUDA installer evaluation.

Run the focused tests:

```powershell
python -m unittest `
  tests.test_desktop_launcher `
  tests.test_app_startup `
  tests.test_runtime_paths `
  tests.test_icon_assets `
  tests.test_model_progress `
  tests.test_preflight `
  tests.test_colorize_preflight `
  tests.test_job_history `
  tests.test_job_history_completion `
  tests.test_recent_jobs_endpoint `
  tests.test_recent_outputs_ui `
  tests.test_preferences `
  tests.test_preferences_api `
  tests.test_upload_preferences_ui
```

Run the batch-focused tests when validating batch builds:

```powershell
python -m unittest `
  tests.test_batch_queue `
  tests.test_batch_upload `
  tests.test_queue_api `
  tests.test_batch_upload_ui `
  tests.test_recent_jobs_endpoint `
  tests.test_recent_outputs_ui
```

Run the v0.4.0 workflow-polish focused tests when validating the current UI
workflow:

```powershell
python -m unittest `
  tests.test_batch_upload_ui `
  tests.test_recent_outputs_ui `
  tests.test_upload_preferences_ui `
  tests.test_responsive_layout_css
```

Run the v0.5.0 diagnostics, robustness, timing, and device-groundwork tests
when validating the current release candidate:

```powershell
python -m unittest `
  tests.test_job_timing `
  tests.test_colorization_timing `
  tests.test_app_startup `
  tests.test_diagnostics_bundle `
  tests.test_colorize_preflight `
  tests.test_runtime_cleanup `
  tests.test_device_detection `
  tests.test_release_version_docs
```

## Build

Expected command:

```powershell
pyinstaller packaging\ColorComic.spec --clean --noconfirm
```

Or use the wrapper:

```powershell
.\packaging\build_windows.ps1
```

The output is:

```text
dist\ColorComic\ColorComic.exe
```

This is a one-folder build. Do not switch it to one-file for this packaging
phase.

## Runtime Behavior

Bundled read-only resources:

- `templates/`
- `static/`
- `vendor/`
- `LICENSE`
- `README.md`
- `THIRD_PARTY_NOTICES.md` or `NOTICE`, if present

The PyInstaller spec also collects project Python modules, including the
runtime helpers under `core\preflight.py`, `core\job_history.py`,
`core\preferences.py`, and `core\batch_queue.py`.

Not bundled:

- `models/weights/`
- downloaded HuggingFace, Google Drive, or Real-ESRGAN model files
- uploads, output PDFs, logs, and cache files

Runtime writable data should continue to go under:

```text
%LOCALAPPDATA%\ColorComic
```

Model downloads should not occur during app startup. They should happen only
after a colorization action requests a model.

## Manual Verification

After building:

```powershell
.\dist\ColorComic\ColorComic.exe
```

Confirm:

- A ColorComic desktop window opens.
- No `uploads`, `output`, or `models\weights` folders appear beside the exe.
- Runtime folders are created under `%LOCALAPPDATA%\ColorComic`.
- Model weights are not downloaded until starting an actual colorization job.
- `/api/preferences` and `/api/recent-jobs` respond in the packaged app.
- `/api/diagnostics` returns safe runtime status without model initialization.
- `/api/diagnostics/bundle` creates a local support ZIP without uploads,
  outputs, model weights, or cache files.
- Preflight errors stop before model loading/download.
- Runtime health preflight reports unwritable folders or low disk before long
  processing starts.
- Recent Outputs lists completed jobs and handles missing outputs.
- Preferences load/save under `%LOCALAPPDATA%\ColorComic\config`.
- Desktop-only Open Folder / Show PDF output actions work for completed jobs.
- Multi-PDF batch upload, Start Batch, queue status polling, queued-job
  cancellation, completed batch output actions, and Recent Outputs batch
  metadata work in the packaged app.
- Processing records job timing, shows page-based ETA only after completed
  pages, and hides stale ETA on failures.
- CPU processing guidance is visible while CPU processing is active and hidden
  on completion or error.
- Orphaned upload cleanup remains conservative and does not remove outputs,
  logs, preferences, model weights, or Recent Outputs history.
- Device capability detection and compute resolution remain CPU-safe: the
  official build resolves to CPU, Preferences stay CPU-only/read-only, and no
  CUDA installer is implied.

## Installer

After the one-folder build exists, compile the unsigned Inno Setup installer:

```powershell
ISCC.exe packaging\inno\ColorComic.iss
```

Or use the wrapper:

```powershell
.\packaging\build_installer.ps1
```

The wrapper discovers `ISCC.exe` automatically. Lookup order:

1. Explicit `-InnoCompiler` argument
2. `ISCC.exe` on `PATH`
3. `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`
4. `C:\Program Files\Inno Setup 6\ISCC.exe`
5. `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`

Example with an explicit compiler path:

```powershell
.\packaging\build_installer.ps1 -InnoCompiler "C:\Program Files\Inno Setup 6\ISCC.exe"
```

If `ISCC.exe` cannot be found, the wrapper prints every checked location and
suggests installing Inno Setup 6, adding `ISCC.exe` to `PATH`, or passing
`-InnoCompiler`.

Before invoking Inno Setup, the wrapper verifies:

- `packaging\inno\ColorComic.iss` exists
- `dist\ColorComic\ColorComic.exe` exists
- `dist\ColorComic` looks like a PyInstaller one-folder build, including the
  `_internal` support directory

If preflight fails, run:

```powershell
.\packaging\build_windows.ps1
```

After Inno Setup completes successfully, the wrapper validates that the expected
installer file exists and is not empty, then prints the installer filename, full
path, and size in MB.

Expected installer output:

```text
packaging\inno\output\ColorComic-Setup-0.5.0-win64-cpu.exe
```

The installer copies `dist\ColorComic` into Program Files, creates a Start Menu
shortcut, offers an optional desktop shortcut, and registers the normal Windows
uninstall entry.

The app, installer, and shortcuts use the shared icon asset at
`static\img\colorcomic.ico`.

Also verify the batch processing workflow before publishing:

- Multi-PDF batch upload accepts valid PDFs and reports per-file preflight
  errors for invalid PDFs.
- **Start Batch** begins sequential queue processing and status polling.
- Queued jobs can be cancelled; running jobs are not cancelled.
- Completed batch jobs support Download, Open Folder, and Show PDF actions.
- Recent Outputs shows batch metadata for batch-origin jobs and preserves
  single-job entries.

For v0.4.0, also verify the workflow polish before publishing:

- Processing page status, progress, completion, and error states are clear.
- Recent Outputs **Remove from list** removes history only, not output files.
- Batch setup shows selected PDFs, count, total size, and supports removing
  selected PDFs before batch creation.
- Auto-only batch messaging appears before users try to create a Reference-mode
  batch.
- Preferences **Reset to Defaults** restores normalized defaults and keeps the
  device CPU-only/read-only.
- Upload, batch, Recent Outputs, and Preferences dynamic statuses have live
  region or alert semantics where appropriate.
- Recent Outputs actions, batch queue actions, and processing completion actions
  wrap cleanly in narrow desktop windows around 900-1200 px wide.

For v0.5.0, also verify diagnostics and robustness before publishing:

- Job timing summaries are recorded for successful jobs and remain
  backward-compatible with existing Recent Outputs history.
- Page-based ETA appears after completed pages, reaches zero at completion, and
  is absent from error payloads.
- CPU guidance says large PDFs may take several minutes during processing only.
- `/api/diagnostics` reports runtime path, platform, disk, model-manager, and
  device status without loading models.
- Diagnostics bundle export includes diagnostics JSON and small logs only.
- Runtime health preflight catches unwritable runtime folders and low disk
  before model loading.
- Orphaned runtime cleanup only removes old abandoned upload/intermediate data.
- `core\device_detection.py` reports CUDA capability safely and
  `resolve_compute_device()` keeps the official CPU build on CPU.
- `requirements-windows-cuda-experimental.txt` and
  `packaging\CUDA_BUILD_PLAN.md` are documented as source/developer planning
  only; the supported installer remains CPU-only.

Also keep verifying the installer workflow hardening:

- `build_installer.ps1` discovers `ISCC.exe` through the documented lookup
  order or reports every checked location.
- Installer preflight fails clearly if the Inno script or PyInstaller
  one-folder output is missing.
- Successful installer builds print the installer filename, full path, and size
  in MB.

Continue to verify the v0.2.0 local workflow hardening:

- Preflight errors stop before model download/load.
- Recent Outputs lists completed jobs and handles missing/deleted outputs.
- Preferences load/save under `%LOCALAPPDATA%\ColorComic\config`.
- Downloaded PDFs still use `<original-name>-colorized.pdf` when the original
  PDF name is available.
- Desktop-only **Open Folder** and **Show PDF** actions open runtime output
  locations.

See `packaging\RELEASE_NOTES.md` for the v0.5.0 release summary.

Uninstall preserves runtime data by default:

```text
%LOCALAPPDATA%\ColorComic
```

To fully remove uploads, outputs, cached model weights, logs, and app config,
delete that folder manually after uninstalling.

This installer is unsigned. Windows SmartScreen and Microsoft Defender may warn
or delay first launch until code signing is added.
