# ColorComic Release Notes

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
