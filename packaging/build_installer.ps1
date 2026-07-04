param(
    [string]$InnoCompiler
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$DistExe = Join-Path $RepoRoot "dist\ColorComic\ColorComic.exe"
$ScriptPath = Join-Path $RepoRoot "packaging\inno\ColorComic.iss"
$CheckedInnoLocations = New-Object System.Collections.Generic.List[string]
$InnoCandidates = New-Object System.Collections.Generic.List[object]

function Add-InnoCandidate {
    param(
        [string]$Source,
        [string]$Path
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        $CheckedInnoLocations.Add("${Source}: <not available>")
        return
    }

    $CheckedInnoLocations.Add("${Source}: $Path")
    $InnoCandidates.Add([pscustomobject]@{
        Source = $Source
        Path = $Path
    })
}

function Format-InnoCompilerNotFoundMessage {
    $checked = ($CheckedInnoLocations | ForEach-Object { "  - $_" }) -join [Environment]::NewLine
    return @"
ISCC.exe was not found.

Checked locations:
$checked

Install Inno Setup 6, add ISCC.exe to PATH, or pass an explicit compiler path:
  .\packaging\build_installer.ps1 -InnoCompiler "C:\Path\To\ISCC.exe"
"@
}

function Join-OptionalPath {
    param(
        [string]$BasePath,
        [string]$ChildPath
    )

    if ([string]::IsNullOrWhiteSpace($BasePath)) {
        return $null
    }
    return Join-Path $BasePath $ChildPath
}

if (-not (Test-Path -LiteralPath $DistExe)) {
    throw "Missing PyInstaller output: $DistExe. Build it first with packaging\build_windows.ps1."
}

if ($InnoCompiler) {
    Add-InnoCandidate "Explicit -InnoCompiler" $InnoCompiler
}

$pathCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($pathCommand) {
    Add-InnoCandidate "PATH" $pathCommand.Source
} else {
    $CheckedInnoLocations.Add("PATH: ISCC.exe <not found>")
}

Add-InnoCandidate "LOCALAPPDATA" (Join-OptionalPath $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
Add-InnoCandidate "ProgramFiles" (Join-OptionalPath $env:ProgramFiles "Inno Setup 6\ISCC.exe")
Add-InnoCandidate "ProgramFiles(x86)" (Join-OptionalPath ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe")

$ResolvedInnoCompiler = $null
foreach ($candidate in $InnoCandidates) {
    if (Test-Path -LiteralPath $candidate.Path) {
        $ResolvedInnoCompiler = (Resolve-Path -LiteralPath $candidate.Path).Path
        Write-Host "Using Inno Setup compiler ($($candidate.Source)): $ResolvedInnoCompiler"
        break
    }
}

if (-not $ResolvedInnoCompiler) {
    throw (Format-InnoCompilerNotFoundMessage)
}

& $ResolvedInnoCompiler $ScriptPath

Write-Host ""
Write-Host "Installer output: packaging\inno\output\ColorComic-Setup-0.2.0-win64-cpu.exe"
