param(
    [string]$InnoCompiler
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$DistDir = Join-Path $RepoRoot "dist\ColorComic"
$DistExe = Join-Path $DistDir "ColorComic.exe"
$InnoDir = Join-Path $RepoRoot "packaging\inno"
$ScriptPath = Join-Path $InnoDir "ColorComic.iss"
$InstallerFileName = "ColorComic-Setup-0.7.0-win64-cpu.exe"
$InstallerOutputPath = Join-Path (Join-Path $InnoDir "output") $InstallerFileName
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

function Format-InstallerPreflightFailedMessage {
    param(
        [System.Collections.Generic.List[string]]$Failures
    )

    $details = ($Failures | ForEach-Object { "  - $_" }) -join [Environment]::NewLine
    return @"
Installer build preflight failed.

$details

Build the PyInstaller one-folder output first:
  .\packaging\build_windows.ps1
"@
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

function Assert-InstallerBuildInputs {
    $failures = New-Object System.Collections.Generic.List[string]
    $internalDir = Join-Path $DistDir "_internal"

    if (-not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) {
        $failures.Add("Missing Inno Setup script: $ScriptPath")
    }

    if (-not (Test-Path -LiteralPath $DistDir -PathType Container)) {
        $failures.Add("Missing PyInstaller one-folder output directory: $DistDir")
    }

    if (-not (Test-Path -LiteralPath $DistExe -PathType Leaf)) {
        $failures.Add("Missing PyInstaller executable: $DistExe")
    }

    if ((Test-Path -LiteralPath $DistDir -PathType Container) -and -not (Test-Path -LiteralPath $internalDir -PathType Container)) {
        $failures.Add("PyInstaller one-folder support directory not found: $internalDir")
    }

    if ($failures.Count -gt 0) {
        throw (Format-InstallerPreflightFailedMessage $failures)
    }
}

function Assert-InstallerOutput {
    if (-not (Test-Path -LiteralPath $InstallerOutputPath -PathType Leaf)) {
        throw "Installer validation failed: expected output was not created: $InstallerOutputPath"
    }

    $installer = Get-Item -LiteralPath $InstallerOutputPath
    if ($installer.Length -le 0) {
        throw "Installer validation failed: output file is empty: $InstallerOutputPath"
    }

    $sizeMb = [math]::Round($installer.Length / 1MB, 2)
    Write-Host ""
    Write-Host "Installer filename: $InstallerFileName"
    Write-Host "Installer path: $($installer.FullName)"
    Write-Host "Installer size: $sizeMb MB"
}

Assert-InstallerBuildInputs

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

Assert-InstallerOutput
