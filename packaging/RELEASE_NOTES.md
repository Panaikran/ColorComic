# ColorComic Release Notes

## v0.7.0 - Project and Queue Management

This release makes long-running colorization batches easier to manage without
changing the existing colorization pipeline.

### Added

- Queue controls to pause, resume, reorder, retry, and remove eligible jobs.
- Retry attempts keep the failed or recovery-required job intact and link the
  fresh queued attempt to it.
- Queue manifest persistence with safe restart recovery: interrupted running
  jobs are marked recovery-required and recovered batches never auto-start.
- Queue counts and concise status summaries for paused, idle, retryable,
  recovery-required, and completed work.

### Unchanged

- The CPU installer remains the official supported release artifact:
  `ColorComic-Setup-0.7.0-win64-cpu.exe`.
- CUDA remains preview-only and is not an official installer.
- No cloud services, telemetry, accounts, auto-update, frontend rewrite, or
  model-family changes were added.

## v0.6.0 - CUDA Preview Readiness

This release prepares a CUDA preview investigation path while keeping the
official supported Windows installer CPU-only.

### Added

- Centralized compute device resolution across model management, Auto mode,
  Reference mode, and optional upscaling paths.
- CUDA runtime robustness improvements for clearer CUDA failure handling,
  cleanup, and CPU-safe fallback behavior where supported.
- Diagnostics fields for CUDA preview status, resolved device, capabilities,
  loaded model device, and fallback reason when available.
- Source CUDA validation tooling through dependency verification output and the
  experimental CUDA requirements file.
- CUDA preview packaging infrastructure:
  - `packaging\build_windows_cuda_preview.ps1`
  - `packaging\ColorComicCudaPreview.spec`
  - `packaging\inno\ColorComicCudaPreview.iss`
  - CUDA preview validation and release-gate documentation.

### Changed

- Packaging documentation now separates the official CPU release from optional
  CUDA preview artifacts.
- Validation docs now require source CUDA validation, packaged NVIDIA-machine
  validation, acceptable non-CUDA machine behavior, model-weight exclusion, and
  artifact-size recording before any CUDA preview artifact can ship.
- Preferences/UI boundaries are documented: CUDA remains hidden/unsupported in
  Preferences for v0.6.0.

### Unchanged

- The CPU installer remains the official supported release.
- The official CPU installer output is
  `ColorComic-Setup-0.6.0-win64-cpu.exe`.
- CUDA remains preview/experimental and is not an official installer.
- No CUDA Preferences controls are exposed.
- No model behavior changes.
- No auto-updater.
- No cloud features or telemetry.
- Model weights are still downloaded on first use and are not bundled.
- Runtime data is still stored under `%LOCALAPPDATA%\ColorComic`.

## v0.5.0 - Diagnostics, Performance Baseline, and CUDA Groundwork

This release improves observability and runtime robustness for the Windows CPU
desktop app while preserving the existing Flask backend, pywebview shell,
PyInstaller one-folder build, Inno Setup installer, local runtime layout, and
CPU-only official release path.

### Added

- Internal job timing summaries for coarse processing phases.
- Page-based ETA during CPU processing after completed pages are available.
- `/api/diagnostics` for safe local runtime status without model loading.
- `/api/diagnostics/bundle` for local support ZIP export without uploads,
  outputs, model weights, or cache files.
- Runtime health preflight checks for writable runtime folders and disk space
  before long processing begins.
- Conservative orphaned upload/intermediate cleanup that preserves outputs,
  logs, preferences, model weights, cache, and Recent Outputs history.
- Device capability detection and CPU-safe compute resolution helpers.
- Experimental CUDA development requirements for source-only developer testing.
- CUDA build evaluation notes for a possible future separate preview installer.

### Changed

- Processing now shows clearer CPU guidance for long-running CPU jobs.
- Single-job processing avoids a small amount of repeated per-page work without
  changing model inference, PDF output, or image quality.
- Packaging validation now covers timing, ETA, diagnostics, runtime robustness,
  cleanup, device capability checks, and CUDA documentation boundaries.
- Installer/package version is now `0.5.0`; expected installer output is
  `packaging\inno\output\ColorComic-Setup-0.5.0-win64-cpu.exe`.

### Unchanged

- The official supported installer remains CPU-only.
- No CUDA installer is shipped.
- No GPU/CUDA Preferences controls are exposed.
- No model behavior changes.
- No auto-updater.
- No cloud features or telemetry.
- Model weights are still downloaded on first use and are not bundled.
- Runtime data is still stored under `%LOCALAPPDATA%\ColorComic`.

## v0.4.0 - Workflow Polish and Accessibility

This release improves the Windows CPU desktop workflow without changing model
behavior, packaging architecture, or local runtime storage.

### Added

- **Reset to Defaults** in Preferences, backed by the local preferences reset
  API.
- Selected-PDF preview for batch setup, including file count, total size, and
  per-file removal before batch creation.
- Clear Auto-only messaging before users try to create a batch in Reference
  mode.

### Changed

- Processing page status, progress, completion, and error states are clearer.
- Recent Outputs can remove a job from local history without deleting output
  files.
- Upload, batch, Recent Outputs, and Preferences dynamic status areas now have
  improved live-region or alert semantics.
- Recent Outputs actions, batch queue actions, and processing completion actions
  wrap better in narrow desktop windows.
- Packaging validation now covers the v0.4.0 workflow polish checks.
- Installer/package version is now `0.4.0`; expected installer output is
  `packaging\inno\output\ColorComic-Setup-0.4.0-win64-cpu.exe`.

### Unchanged

- No model behavior changes.
- No CUDA build.
- No auto-updater.
- No cloud features or telemetry.
- Model weights are still downloaded on first use and are not bundled.
- Runtime data is still stored under `%LOCALAPPDATA%\ColorComic`.

## v0.3.0 - Batch Processing and Queue

This release adds conservative Auto-mode batch processing while preserving the
Windows CPU desktop architecture, local Flask backend, one-folder PyInstaller
build, and first-use model download behavior.

### Added

- Multi-PDF batch upload for Auto mode.
- Sequential queue processing with Start Batch and visible per-job statuses.
- Queued-job cancellation for jobs that have not started yet.
- Completed batch job actions:
  - Download PDF
  - Open Folder in desktop mode
  - Show PDF in desktop mode
- Recent Outputs batch metadata so batch-origin jobs show their batch label
  while existing single-job history remains compatible.

### Changed

- Packaging validation now covers batch upload, batch preflight errors, queue
  polling, queued-job cancellation, completed batch output actions, and Recent
  Outputs batch metadata.
- PyInstaller packaging now explicitly includes `core.batch_queue`.
- Installer/package version is now `0.3.0`; expected installer output is
  `packaging\inno\output\ColorComic-Setup-0.3.0-win64-cpu.exe`.

### Unchanged

- No model behavior changes.
- No CUDA build.
- No auto-updater.
- No cloud features or telemetry.
- Model weights are still downloaded on first use and are not bundled.
- Runtime data is still stored under `%LOCALAPPDATA%\ColorComic`.

## v0.2.1 - Installer Workflow Maintenance

This maintenance release keeps end-user app behavior unchanged and improves the
Windows CPU installer build workflow for release operators.

### Changed

- `packaging\build_installer.ps1` now discovers `ISCC.exe` automatically from
  an explicit `-InnoCompiler` argument, `PATH`, and common Inno Setup 6 install
  locations.
- Missing-compiler diagnostics now list every checked location and include
  recovery guidance.
- Installer builds now run preflight checks for the Inno script, PyInstaller
  one-folder output, `ColorComic.exe`, and the `_internal` support directory
  before invoking Inno Setup.
- After Inno Setup completes, the installer wrapper validates that the expected
  installer file exists, is not empty, and prints the filename, full path, and
  size in MB.
- Packaging documentation and validation checklists now describe the improved
  installer workflow.
- Installer/package version is now `0.2.1`; expected installer output is
  `packaging\inno\output\ColorComic-Setup-0.2.1-win64-cpu.exe`.

### Unchanged

- No app UI changes.
- No model behavior changes.
- No PyInstaller spec changes.
- No installer format changes.
- No CUDA build.
- No auto-updater.

## v0.2.0 - Local Workflow Hardening

This release keeps the Windows CPU desktop architecture stable while improving
local reliability before and after colorization. It keeps the Flask backend,
pywebview desktop shell, PyInstaller one-folder build, Inno Setup installer,
CPU-only default packaging, and first-use model downloads.

### Added

- Preflight checks for uploaded PDFs, output directories, and Reference mode
  images before model download/load begins.
- Local Recent Outputs history stored under `%LOCALAPPDATA%\ColorComic`.
- Recent Outputs list on the upload page with Download plus desktop-only output
  actions when files are still available.
- Desktop-only **Show PDF in Folder** action for completed outputs.
- Local Preferences storage and API under
  `%LOCALAPPDATA%\ColorComic\config\preferences.json`.
- Compact Preferences section for safe local defaults:
  - default colorization mode: Auto or Reference
  - open output folder after completion
  - CPU-only device shown read-only

### Changed

- Preflight failures now stop before long CPU/model work and surface clearer
  user-facing messages.
- PyInstaller packaging now explicitly includes the v0.2.0 runtime helper
  modules: `core.preflight`, `core.job_history`, and `core.preferences`.
- Packaged smoke validation now checks `/api/preferences`, `/api/recent-jobs`,
  and executable-local runtime folders.
- Installer/package version is now `0.2.0`; expected installer output is
  `packaging\inno\output\ColorComic-Setup-0.2.0-win64-cpu.exe`.

### Unchanged

- No model behavior changes.
- No CUDA build.
- No auto-updater.
- No cloud features or telemetry.
- Model weights are still downloaded on first use and are not bundled.
- Runtime data is still stored under `%LOCALAPPDATA%\ColorComic`.

### Validation Focus

- Invalid PDFs, empty PDFs, invalid Reference images, and unwritable output
  folders fail before model download/load.
- Recent Outputs lists completed jobs newest-first and handles deleted outputs
  gracefully.
- Download, Open Folder, and Show PDF output actions work in desktop mode.
- Preferences load/save locally, expose no GPU/CUDA option, and recover from
  missing or corrupt preferences files.
- Packaged builds still write runtime data only under
  `%LOCALAPPDATA%\ColorComic` and do not bundle model weights.

## v0.1.1 - Windows CPU Desktop Polish

This is a small polish and bugfix release on top of the v0.1.0 Windows CPU
desktop app. It keeps the same Flask backend, pywebview desktop shell,
PyInstaller one-folder build, Inno Setup installer, and CPU-only default
packaging.

### Added

- Shared ColorComic icon asset for favicon, packaged app, installer, and
  shortcuts.
- Desktop-only **Open Output Folder** action after processing completes.
- Visible processing-page messages for first-run model download and model-load
  phases.

### Changed

- Downloaded PDFs now use a source-aware filename such as
  `<original-name>-colorized.pdf` when the uploaded PDF name is available.
- Installer/package version is now `0.1.1`; expected installer output is
  `packaging\inno\output\ColorComic-Setup-0.1.1-win64-cpu.exe`.

### Unchanged

- No model behavior changes.
- No CUDA build.
- No auto-updater.
- Model weights are still downloaded on first use and are not bundled.
- Runtime data is still stored under `%LOCALAPPDATA%\ColorComic`.

### Validation Focus

- Favicon and Windows icons appear correctly.
- Download PDF works in browser and pywebview desktop mode.
- Open Output Folder opens the runtime job directory in desktop mode.
- First-run model download/loading messages are visible in Auto and Reference
  modes.
