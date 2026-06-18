param(
    [string]$InnoCompiler
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$DistExe = Join-Path $RepoRoot "dist\ColorComic\ColorComic.exe"
$ScriptPath = Join-Path $RepoRoot "packaging\inno\ColorComic.iss"

if (-not (Test-Path -LiteralPath $DistExe)) {
    throw "Missing PyInstaller output: $DistExe. Build it first with packaging\build_windows.ps1."
}

if (-not $InnoCompiler) {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) {
        $InnoCompiler = $command.Source
    }
}

if (-not $InnoCompiler) {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            $InnoCompiler = $candidate
            break
        }
    }
}

if (-not $InnoCompiler -or -not (Test-Path -LiteralPath $InnoCompiler)) {
    throw "ISCC.exe not found. Install Inno Setup 6 or pass -InnoCompiler <path-to-ISCC.exe>."
}

& $InnoCompiler $ScriptPath

Write-Host ""
Write-Host "Installer output: packaging\inno\output\ColorComic-Setup-0.1.0-win64-cpu.exe"
