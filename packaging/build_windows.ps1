param(
    [switch]$SkipDependencyCheck
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $VenvPython -PathType Leaf) {
    $PythonExe = (Resolve-Path -LiteralPath $VenvPython).Path
} else {
    Write-Warning "No repo virtual environment found at $VenvPython. Falling back to python on PATH."
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Python was not found. Create .venv with the packaging dependencies, then rerun .\packaging\build_windows.ps1."
    }
    $PythonExe = $pythonCommand.Source
}

Write-Host "Using Python: $PythonExe"

if (-not $SkipDependencyCheck) {
    & $PythonExe scripts\verify_dependency_imports.py
}

& $PythonExe -m PyInstaller packaging\ColorComic.spec --clean --noconfirm

Write-Host ""
Write-Host "Build complete: dist\ColorComic\ColorComic.exe"
Write-Host "Run with: .\dist\ColorComic\ColorComic.exe"
