$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $appRoot ".venv\Scripts\python.exe"
$python313 = Join-Path $env:LocalAppData "Programs\Python\Python313\python.exe"

if (-not (Test-Path $python313) -and -not (Get-Command py -ErrorAction SilentlyContinue)) {
    $installer = Get-ChildItem (Join-Path $PSScriptRoot "..\installers\Python*.exe") -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($installer) {
        Write-Host "Installing bundled Python 3.13..."
        Start-Process -FilePath $installer.FullName -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1" -Wait
    } else {
        Write-Host "Bundled Python installer not found. Installing Python 3.13 with winget..."
        winget install --id Python.Python.3.13 --exact --accept-package-agreements --accept-source-agreements
    }
}

if (-not (Test-Path $python313)) {
    $pythonCommand = Get-Command py -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { throw "Python 3.13 was not found after installation." }
    $pythonLauncher = $pythonCommand.Source
    $python313 = & $pythonLauncher -3.13 -c 'import sys; print(sys.executable)'
    $python313 = $python313.Trim()
}

if (-not (Test-Path $venvPython)) {
    & $python313 -m venv (Join-Path $appRoot ".venv")
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e $appRoot
Write-Host "Environment installation completed. Copy config.example.yaml to config.local.yaml, then fill in EMS and Webhook settings."
