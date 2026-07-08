# ColorComic Clean-Machine Validation

This checklist validates the PyInstaller one-folder Windows CPU desktop build
and unsigned Inno Setup installer. Use it for `dist\ColorComic\ColorComic.exe`
and the current unsigned installer output.

## Build Baseline

- Expected output path: `dist\ColorComic\ColorComic.exe`
- Expected installer path:
  `packaging\inno\output\ColorComic-Setup-0.3.0-win64-cpu.exe`
- Expected build type: PyInstaller one-folder, not one-file
- Observed local output size: about 2.17 GB for the full `dist\ColorComic`
  folder
- Observed local build duration: about 19-31 minutes on this machine, depending
  on PyInstaller cache state and ML package analysis
- Model weights are not bundled. First model use downloads into
  `%LOCALAPPDATA%\ColorComic\models\weights`

## Local Smoke Test

Run from the repo root after building:

```powershell
.\packaging\smoke_dist.ps1
```

Expected result:

- `HealthOk` is `True`
- `PreferencesOk` is `True`
- `RecentJobsOk` is `True`
- `Service` is `ColorComic`
- `MainWindowTitle` is `ColorComic`
- `MainWindowHandle` is nonzero
- `RuntimePath` points to `%LOCALAPPDATA%\ColorComic`
- `ExeLocalRuntimeFolders` is empty
- The script stops `ColorComic.exe` before returning

Also confirm no repo-local or executable-local runtime folders appear:

```powershell
Get-ChildItem .\dist\ColorComic -Force |
  Where-Object { $_.Name -in @("uploads", "output", "models", "logs", "cache") }
```

Expected: no results.

## Installer Build Workflow

Run the installer wrapper after the PyInstaller one-folder build exists:

```powershell
.\packaging\build_installer.ps1
```

Expected behavior:

- The wrapper finds `ISCC.exe` through the explicit `-InnoCompiler` argument,
  `PATH`, or one of the common Inno Setup 6 install locations.
- If `ISCC.exe` is missing, the error lists every checked location and gives
  recovery guidance.
- Before invoking Inno Setup, the wrapper confirms
  `packaging\inno\ColorComic.iss`, `dist\ColorComic\ColorComic.exe`, and the
  PyInstaller one-folder support directory exist.
- If preflight fails, the error suggests running
  `.\packaging\build_windows.ps1` first.
- After Inno Setup completes, the wrapper confirms the installer exists, is not
  empty, and prints the filename, full path, and size in MB.

Expected installer output:

```text
packaging\inno\output\ColorComic-Setup-0.3.0-win64-cpu.exe
```

## Clean Windows VM Or Different User

Validate on a clean Windows VM or at least a different Windows user account.
This catches missing user-profile assumptions, WebView2 availability, Defender
behavior, and permissions issues that a developer machine can hide.

1. Copy the whole `dist\ColorComic` folder to a path with spaces, for example:

   ```text
   C:\Users\<User>\Desktop\ColorComic Test\ColorComic
   ```

2. Launch:

   ```powershell
   .\ColorComic.exe
   ```

3. Confirm a desktop window opens with title `ColorComic`.

4. Confirm WebView2 availability:
   - If the app window opens normally, WebView2 is present.
   - If pywebview reports a runtime/browser backend error, install Microsoft
     Edge WebView2 Runtime and retry.

5. Confirm `/api/health` works:
   - Use Task Manager or PowerShell to find the listening localhost port.
   - Run:

     ```powershell
     Invoke-RestMethod http://127.0.0.1:<port>/api/health
     ```

   - Expected: `ok: true`, `service: ColorComic`.

6. Confirm static/templates load:
   - Upload page renders with styles.
   - Browser favicon loads without a 404.
   - The desktop window, executable, installer, Start Menu shortcut, and
     optional desktop shortcut use the ColorComic icon where Windows exposes
     one.
   - Buttons, radio controls, upload area, and reference-mode notice are visible.
   - Browser/devtools console is not required; this is a visual check.

7. Confirm runtime writes go only to:

   ```text
   %LOCALAPPDATA%\ColorComic
   ```

   Expected folders after startup:

   ```text
   uploads
   output
   models\weights
   models\weights\manganinja
   cache\huggingface
   logs
   config
   ```

8. Confirm no writes beside the executable:
   - No `uploads`, `output`, `models\weights`, `logs`, or `cache` folders under
     `dist\ColorComic`
   - No model weight files inside `dist\ColorComic`

9. Confirm no model download on startup:
   - Start app and wait 1-2 minutes without uploading a PDF.
   - `%LOCALAPPDATA%\ColorComic\models\weights` should contain directories only,
     not files such as `generator.zip`, `net_rgb.pth`, or MangaNinja `.pth`
     files.

10. Preflight error handling:
    - Try a damaged or renamed non-PDF file with a `.pdf` extension.
      Expected: processing stops before model download/load and the UI says to
      choose a valid PDF.
    - Try an empty PDF with no pages, if available.
      Expected: the UI says to choose a PDF with at least one page.
    - In Reference mode, start without a valid reference image or with a
      corrupted image file.
      Expected: processing stops before MangaNinja or SD 1.5 loading and the UI
      says to choose a valid reference image.
    - If output folder permissions can be restricted in the test account,
      confirm the UI reports that ColorComic cannot write to the output folder.
    - In all cases, confirm no model weights are downloaded as part of the
      preflight failure.

11. Preferences:
    - Confirm the upload page shows a compact Preferences section.
    - Confirm **Default Colorization Mode** can be saved as Auto or Reference.
    - Confirm **Open output folder after completion** can be checked and saved.
    - Confirm device preference is shown as CPU only/read-only.
    - Confirm there are no GPU/CUDA preference controls.
    - Close and reopen the app.
    - Expected: saved preferences load, missing/corrupt `preferences.json`
      falls back to defaults without breaking the upload page, and
      `%LOCALAPPDATA%\ColorComic\config\preferences.json` is the only
      preferences file written.

12. Batch processing:
    - Select multiple valid PDFs on the upload page.
      Expected: the UI creates a batch instead of starting processing
      immediately.
    - Include one damaged or unreadable PDF in the selection.
      Expected: valid PDFs are accepted, the invalid file shows a concise
      per-file preflight error, and no model loading/download starts yet.
    - Click **Start Batch**.
      Expected: queued jobs process sequentially and the UI polls queue status.
    - Confirm queue statuses are visible as jobs move through `queued`,
      `running`, `completed`, `failed`, and `cancelled` where applicable.
    - Cancel a job that is still `queued`.
      Expected: the job becomes `cancelled`, running jobs are not cancelled,
      and uploaded/runtime folders are not deleted.
    - For each completed batch job, confirm Download PDF works.
    - In desktop mode, confirm completed batch jobs show working **Open Folder**
      and **Show PDF** actions.
    - Return to the upload page.
      Expected: Recent Outputs shows completed batch jobs with a small batch
      identifier/label while older single-job entries remain unchanged.

13. First-run model download:
    - Use a tiny one-page black-and-white PDF.
    - Upload it in auto mode.
    - Confirm the app downloads auto-mode weights into
      `%LOCALAPPDATA%\ColorComic\models\weights`.
    - Confirm the processing page shows visible messages such as
      `Downloading auto colorization model...` and
      `Loading auto colorization model...`.
    - Confirm the UI does not freeze permanently while the download/model load
      happens.

14. Tiny one-page PDF processing:
    - Process a one-page PDF in auto mode.
    - Confirm the processing page receives progress updates.
    - Confirm preview image loads.
    - Confirm Download PDF works in the desktop window.
    - Confirm the downloaded filename is source-aware, for example
      `<original-name>-colorized.pdf`, when the uploaded PDF name is known.
    - Confirm browser-mode download still works if testing with `python app.py`.
    - Confirm the desktop-only **Open Output Folder** button opens
      `%LOCALAPPDATA%\ColorComic\output\<job_id>` in Explorer.
    - Confirm the desktop-only **Show PDF in Folder** button reveals
      `%LOCALAPPDATA%\ColorComic\output\<job_id>\colorized.pdf` in Explorer.
    - Confirm output files are under `%LOCALAPPDATA%\ColorComic\output`.

15. Recent Outputs:
    - Return to the upload page after at least one successful job.
    - Confirm Recent Outputs lists newest-first completed jobs.
    - Confirm each available safe output shows Download.
    - In desktop mode, confirm **Show PDF** reveals the generated PDF in
      Explorer and **Open Folder** opens the job folder.
    - Delete or move one output PDF and reopen the app.
    - Expected: the missing output is marked unavailable instead of crashing.
    - If the job history file is missing or corrupt, expected: Recent Outputs
      shows the empty state or a non-blocking load failure, not a startup crash.

16. Reference-mode first-run progress:
    - Upload a PDF with a colored reference page.
    - Confirm the processing page shows visible messages such as
      `Downloading MangaNinja weights...`, `Loading SD 1.5 components...`,
      and `Loading Reference mode model...`.
    - Confirm Reference mode can still finish after the first-run downloads.

17. v0.4.0 workflow polish:
    - Processing page clarity:
      - Confirm model download/load messages are visible.
      - Confirm page progress reads clearly, including completed pages.
      - Confirm backend errors show the relevant processing step when available.
      - Confirm interrupted SSE/connection failures show a visible error instead
        of leaving the spinner active indefinitely.
    - Recent Outputs removal:
      - Click **Remove from list** on a completed output.
      - Expected: the history entry disappears, output files remain on disk, and
        the list/empty state updates without deleting runtime output folders.
    - Batch setup preview/removal workflow:
      - Select multiple PDFs.
      - Expected: selected filenames, file count, and total size are shown before
        batch creation.
      - Remove one selected PDF.
      - Expected: selected-file count and total size update.
      - Remove until one PDF remains.
      - Expected: the upload page returns to the normal single-PDF workflow.
      - Remove all PDFs.
      - Expected: file info clears and upload is disabled.
    - Auto-only batch messaging:
      - Select multiple PDFs while Reference mode is selected.
      - Expected: the UI states that batch processing supports Auto mode only,
        Reference mode is single-PDF only, and batch creation stays disabled
        until Auto mode is selected.
    - Preferences reset:
      - Change preferences, then click **Reset to Defaults**.
      - Expected: preferences return to normalized defaults, the status message
        confirms success, and device remains CPU only/read-only.
      - If the reset API is unavailable, expected: the Preferences panel shows a
        concise non-blocking error.
    - Accessibility:
      - Confirm upload status, batch status/counts, Recent Outputs status/error,
        and Preferences status are announced through live regions.
      - Confirm Recent Outputs error text uses alert semantics.
      - Confirm dynamic buttons such as Download, Show PDF, Open Folder, Remove,
        and queued-job Cancel have clear accessible names.
    - Responsive layout smoke checks:
      - Resize the desktop window to about 900-1200 px wide.
      - Expected: Recent Outputs actions, batch queue actions, and processing
        completion actions wrap instead of overflowing.
      - Expected: long PDF filenames wrap or remain contained while action
        buttons stay usable.

18. Failed network download handling:
    - Disconnect the network or block access to Google Drive/HuggingFace.
    - Start a colorization job that needs a missing model.
    - Expected: job enters an error state and the UI shows a useful failure
      instead of hanging indefinitely.

19. App close releases process and port:
    - Close the ColorComic window.
    - Confirm `ColorComic.exe` exits.
    - Confirm the localhost listening port is released:

      ```powershell
      Get-Process ColorComic -ErrorAction SilentlyContinue
      Get-NetTCPConnection -State Listen |
        Where-Object { $_.OwningProcess -eq <old-process-id> }
      ```

20. SmartScreen/Defender notes:
    - Unsigned builds may show Microsoft Defender SmartScreen warnings.
    - Defender may scan or delay first launch because the folder is large and
      contains ML/runtime DLLs.
    - Record whether warnings are acceptable for internal testing. Code signing
      should be handled before wider distribution.

## Blockers Before Release

Do not publish the one-folder build or installer if any of these fail:

- The exe does not launch on a clean Windows user/VM.
- WebView2 is missing and the app does not report the issue clearly enough.
- `/api/health` never becomes ready.
- Static/templates fail to load.
- Runtime files are written beside the executable.
- Model weights are bundled or downloaded at startup.
- Browser favicon or Windows app/shortcut icons are missing or show stale
  generic icons after a fresh install.
- Download PDF fails in pywebview or browser mode.
- Open Output Folder fails to open the runtime job output folder in desktop
  mode.
- Show PDF in Folder fails to reveal the generated runtime PDF in desktop mode.
- Recent Outputs cannot list completed jobs or crashes on missing/corrupt
  history.
- Batch upload, Start Batch, queued-job cancellation, queue polling, completed
  batch output actions, or Recent Outputs batch metadata fail in the packaged
  app.
- Preferences cannot load/save, exposes GPU/CUDA options, or writes outside
  `%LOCALAPPDATA%\ColorComic\config`.
- Preferences reset does not restore normalized defaults or fails silently.
- Processing page status/error clarity regresses or dynamic status text is not
  exposed to assistive technologies.
- Recent Outputs removal deletes output files instead of only removing history.
- Batch selected-file preview/removal, Auto-only batch messaging, or narrow-window
  action wrapping fails in the packaged app.
- Model download/loading progress is invisible during first-run auto or
  reference model setup.
- Closing the window leaves `ColorComic.exe` or the Flask port running.
- A tiny one-page PDF cannot complete in auto mode after first-run model
  download.
