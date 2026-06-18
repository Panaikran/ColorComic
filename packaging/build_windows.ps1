param(
    [switch]$SkipDependencyCheck
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

if (-not $SkipDependencyCheck) {
    python scripts\verify_dependency_imports.py
}

pyinstaller packaging\ColorComic.spec --clean --noconfirm

Write-Host ""
Write-Host "Build complete: dist\ColorComic\ColorComic.exe"
Write-Host "Run with: .\dist\ColorComic\ColorComic.exe"
