param([string]$AppRoot = (Resolve-Path "$PSScriptRoot\..\..").Path,[string]$ConfigPath = "config.sqlserver.local.yaml",[string]$PythonExe = "python",[string]$LogDirectory = (Join-Path $AppRoot "logs"))
$env:PYTHONPATH = Join-Path $AppRoot "src"
New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
Set-Location $AppRoot
& $PythonExe -u -m wecom_sales_webhook_bot.cli run-server --config (Join-Path $AppRoot $ConfigPath) 2>&1 | Tee-Object -FilePath (Join-Path $LogDirectory "web-console.log")
