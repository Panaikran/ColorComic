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

Run the focused tests:

```powershell
python -m unittest tests.test_desktop_launcher tests.test_app_startup tests.test_runtime_paths
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

## Installer

After the one-folder build exists, compile the unsigned Inno Setup installer:

```powershell
ISCC.exe packaging\inno\ColorComic.iss
```

Or use the wrapper:

```powershell
.\packaging\build_installer.ps1
```

Expected installer output:

```text
packaging\inno\output\ColorComic-Setup-0.1.1-win64-cpu.exe
```

The installer copies `dist\ColorComic` into Program Files, creates a Start Menu
shortcut, offers an optional desktop shortcut, and registers the normal Windows
uninstall entry.

The app, installer, and shortcuts use the shared icon asset at
`static\img\colorcomic.ico`.

Uninstall preserves runtime data by default:

```text
%LOCALAPPDATA%\ColorComic
```

To fully remove uploads, outputs, cached model weights, logs, and app config,
delete that folder manually after uninstalling.

This installer is unsigned. Windows SmartScreen and Microsoft Defender may warn
or delay first launch until code signing is added.
