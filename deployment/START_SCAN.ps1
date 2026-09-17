$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $appRoot ".venv\Scripts\python.exe"
$configPath = Join-Path $appRoot "config.local.yaml"
if (-not (Test-Path $pythonExe)) { throw "Virtual environment not found. Run INSTALL_ENVIRONMENT.ps1 first." }
if (-not (Test-Path $configPath)) { throw "config.local.yaml not found. Copy config.example.yaml and edit it first." }
$env:PYTHONPATH = Join-Path $appRoot "src"
Set-Location $appRoot
& $pythonExe -u -m wecom_sales_webhook_bot.cli schedule --config $configPath
