$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $appRoot "var\schedule.pid"
if (Test-Path $pidFile) {
    $processId = [int](Get-Content $pidFile -Raw)
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    Write-Host "Scan process stopped."
} else { Write-Host "No scan PID file found." }
