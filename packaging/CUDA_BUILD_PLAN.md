# CUDA Build Evaluation

This note records what would be required to ship an official CUDA-enabled
Windows build. It does not enable CUDA and does not change the official CPU
release.

## Current Packaging Pipeline

- `requirements-windows-cpu.txt` installs `torch==2.3.1+cpu` and
  `torchvision==0.18.1+cpu` from the PyTorch CPU wheel index.
- `packaging/ColorComic.spec` builds a PyInstaller one-folder desktop app from
  `desktop.py`, collects dynamic libraries from `torch`, `torchvision`, `cv2`,
  `numpy`, and `scipy`, and excludes unrelated large packages.
- `packaging/build_windows.ps1` verifies dependencies with the selected Python
  environment, then runs `python -m PyInstaller packaging\ColorComic.spec`.
- `packaging/build_installer.ps1` expects `dist\ColorComic\ColorComic.exe`,
  validates the one-folder output, then runs Inno Setup.
- `packaging/inno/ColorComic.iss` packages `dist\ColorComic` into Program
  Files and emits `ColorComic-Setup-{version}-win64-cpu.exe`.

## CUDA Dependency Baseline

The experimental source-only CUDA file currently pins the same app stack as the
CPU file, but swaps PyTorch to:

- `torch==2.3.1+cu121`
- `torchvision==0.18.1+cu121`
- `--extra-index-url https://download.pytorch.org/whl/cu121`

PyTorch documents CUDA 12.1 wheels for Windows/Linux in its previous-version
install table. NVIDIA documents CUDA 12.1 Windows driver minimums at driver
`531.14` for CUDA 12.1 GA/Update 1, while CUDA 12.x minor-version compatibility
starts at the broader `>=525` driver range. Validate the exact requirement
against the selected PyTorch/CUDA wheel before release.

References:

- https://pytorch.org/get-started/previous-versions/
- https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html

## Expected CUDA DLL Impact

A CUDA build should expect PyInstaller to collect additional Torch CUDA runtime
libraries from the installed wheel environment, including libraries similar to:

- `torch_cuda*.dll`, `c10_cuda.dll`
- CUDA runtime DLLs such as `cudart64_*.dll`
- CUDA math/runtime libraries such as `cublas64_*.dll`, `cublasLt64_*.dll`,
  `cufft64_*.dll`, `curand64_*.dll`, `cusolver64_*.dll`,
  `cusparse64_*.dll`, `nvrtc64_*.dll`, and `nvJitLink*.dll`
- cuDNN DLLs if required and present in the selected PyTorch wheel set

The exact list must be measured from a clean CUDA build environment. Do not
hand-edit DLL lists unless PyInstaller misses a required runtime library.

## Size And Installer Considerations

Expected impact is large:

- CUDA PyTorch wheels are much larger than CPU wheels.
- The one-folder `dist\ColorComic` output may grow by multiple gigabytes once
  CUDA runtime libraries are collected.
- The compressed Inno installer may still grow by roughly 1.5-3+ GB depending
  on the selected CUDA wheel and collected DLL set.
- Antivirus and SmartScreen scanning may take longer for a much larger unsigned
  installer.

Measure actual `dist\ColorComic` and installer size before any CUDA preview.

## PyInstaller Considerations

- Build CUDA from a separate virtual environment that installs
  `requirements-windows-cuda-experimental.txt`.
- Use a separate spec/output name, for example `ColorComicCuda.spec` and
  `dist\ColorComicCuda`, to avoid mixing CPU and CUDA artifacts.
- Keep model weights out of the bundle.
- Confirm `collect_dynamic_libs("torch")` captures all CUDA DLLs.
- Run a packaged smoke test on a machine with a compatible NVIDIA driver.
- Verify CPU fallback still works when CUDA is unavailable or fails at runtime.

## Hardware Guidance

Minimum guidance for any future CUDA preview:

- NVIDIA GPU with a driver compatible with the selected PyTorch CUDA wheel.
- For the current CUDA 12.1 experiment, require Windows NVIDIA driver `531.14`
  or newer, then retest against the final wheel choice.
- Auto mode: recommend at least 4 GB VRAM; 6 GB+ preferred for larger PDFs.
- Reference mode: recommend at least 8 GB VRAM; 12 GB+ preferred because SD 1.5
  components and MangaNinja weights are much heavier.

## Recommendation

Keep v0.5.0 CPU-only.

If CUDA ships, prefer a separate CUDA preview installer in v0.6.0 or later:

- `ColorComic-Setup-{version}-win64-cpu.exe`
- `ColorComic-Setup-{version}-win64-cuda-preview.exe`

Do not use a unified installer yet. A unified installer would need a larger
download for all users, more complex dependency selection, more failure modes,
and more validation paths. The current CPU installer should remain the stable
default until CUDA behavior, size, fallback, and clean-machine validation are
proven separately.
