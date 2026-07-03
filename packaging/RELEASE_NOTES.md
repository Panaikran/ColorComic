# ColorComic Release Notes

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
