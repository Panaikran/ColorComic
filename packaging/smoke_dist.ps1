param(
    [string]$ExePath = ".\dist\ColorComic\ColorComic.exe",
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ExePath)) {
    throw "Executable not found: $ExePath"
}

$resolvedExe = Resolve-Path -LiteralPath $ExePath
$process = Start-Process -FilePath $resolvedExe -PassThru
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$health = $null
$port = $null

try {
    while ((Get-Date) -lt $deadline) {
        $process.Refresh()
        if ($process.HasExited) {
            throw "ColorComic exited before /api/health became ready."
        }

        $conn = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.OwningProcess -eq $process.Id -and $_.LocalAddress -eq "127.0.0.1" } |
            Select-Object -First 1

        if ($conn) {
            $port = $conn.LocalPort
            try {
                $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/health" -TimeoutSec 5
                if ($health.ok) {
                    break
                }
            } catch {
                Start-Sleep -Seconds 2
            }
        } else {
            Start-Sleep -Seconds 2
        }
    }

    if (-not $health -or -not $health.ok) {
        throw "Timed out waiting for /api/health."
    }

    Start-Sleep -Seconds 5
    $process.Refresh()

    [pscustomobject]@{
        ProcessId        = $process.Id
        Port             = $port
        HealthOk         = [bool]$health.ok
        Service          = $health.service
        MainWindowHandle = $process.MainWindowHandle
        MainWindowTitle  = $process.MainWindowTitle
        Responding       = $process.Responding
        RuntimePath      = Join-Path $env:LOCALAPPDATA "ColorComic"
    }
}
finally {
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
}
