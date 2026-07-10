param(
    [string]$PythonExe
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

if (-not $PythonExe) {
    $VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $VenvPython -PathType Leaf) {
        $PythonExe = (Resolve-Path -LiteralPath $VenvPython).Path
    } else {
        Write-Warning "No repo virtual environment found at $VenvPython. Falling back to python on PATH."
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonCommand) {
            throw "Python was not found. Create a CUDA preview virtual environment, then rerun .\packaging\build_windows_cuda_preview.ps1."
        }
        $PythonExe = $pythonCommand.Source
    }
} elseif (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Selected Python does not exist: $PythonExe"
} else {
    $PythonExe = (Resolve-Path -LiteralPath $PythonExe).Path
}

Write-Host "Using Python: $PythonExe"
Write-Host "Checking CUDA preview build prerequisites..."

$CudaProbe = @'
import sys

try:
    import torch
except Exception as exc:
    print(f"ERROR: torch import failed: {exc}", file=sys.stderr)
    sys.exit(20)

try:
    from core.device_detection import detect_device_capabilities
    capabilities = detect_device_capabilities(torch)
except Exception as exc:
    print(f"ERROR: device capability probe failed: {exc}", file=sys.stderr)
    sys.exit(21)

torch_version = capabilities.get("torch_version") or getattr(torch, "__version__", "unknown")
cuda_version = capabilities.get("cuda_version") or getattr(getattr(torch, "version", None), "cuda", None)
cuda_available = bool(capabilities.get("cuda_available"))
gpus = capabilities.get("gpus") or []

print(f"torch version: {torch_version}")
print(f"torch CUDA build: {cuda_version or 'none'}")
print(f"CUDA available: {cuda_available}")

if gpus:
    for index, gpu in enumerate(gpus):
        name = gpu.get("name") or f"GPU {index}"
        total_memory = gpu.get("total_memory")
        if isinstance(total_memory, int):
            print(f"CUDA GPU {index}: {name} ({total_memory / (1024 ** 3):.1f} GB VRAM)")
        else:
            print(f"CUDA GPU {index}: {name} (VRAM unknown)")
else:
    print("CUDA GPU: none reported")

if not cuda_version:
    print("ERROR: CUDA preview build requires a CUDA-enabled Torch wheel. CPU-only Torch is not supported.", file=sys.stderr)
    sys.exit(30)

if not cuda_available:
    print("ERROR: CUDA preview build requires torch.cuda.is_available() to be true on the validation machine.", file=sys.stderr)
    sys.exit(31)
'@

$CudaProbe | & $PythonExe -
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$SpecPath = Join-Path $RepoRoot "packaging\ColorComicCudaPreview.spec"
if (-not (Test-Path -LiteralPath $SpecPath -PathType Leaf)) {
    Write-Error "CUDA preview PyInstaller spec is not implemented yet: packaging\ColorComicCudaPreview.spec. Preflight passed, but this skeleton stops before packaging."
    exit 40
}

Write-Host "CUDA preview prerequisites passed."
Write-Host "Model weights must remain excluded from the CUDA preview bundle."

& $PythonExe -m PyInstaller packaging\ColorComicCudaPreview.spec --clean --noconfirm

Write-Host ""
Write-Host "CUDA preview build complete: dist\ColorComicCudaPreview\ColorComicCudaPreview.exe"
