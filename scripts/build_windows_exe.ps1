$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv (Join-Path $repoRoot ".venv")
    } else {
        $pythonCommand = Get-Command python -ErrorAction Stop
        & $pythonCommand.Source -m venv (Join-Path $repoRoot ".venv")
    }
    if ($LASTEXITCODE -ne 0) { throw "Creating the project virtual environment failed." }
}

$python = $venvPython
& $python -c "import sys; assert sys.version_info >= (3, 12), 'Python 3.12 or newer is required.'"
if ($LASTEXITCODE -ne 0) { throw "Python 3.12 or newer is required to build the EXE." }
& $python -m pip install -e ".[build]"
if ($LASTEXITCODE -ne 0) { throw "Installing Windows build dependencies failed." }

$entry = Join-Path $repoRoot "scripts\desktop_gui_entry.py"
$dist = Join-Path $repoRoot "dist"
$work = Join-Path $repoRoot "build"
& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "SalesWebhook" `
    --paths (Join-Path $repoRoot "src") `
    --collect-all wecom_sales_webhook_bot `
    --collect-all win32com `
    --collect-all PIL `
    --collect-all yaml `
    --collect-all sqlalchemy `
    --hidden-import pyodbc `
    --hidden-import pythoncom `
    --hidden-import pywintypes `
    --hidden-import win32timezone `
    --distpath $dist `
    --workpath $work `
    $entry
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

$sourceExe = Join-Path $dist "SalesWebhook.exe"
$deliveryName = -join @([char]0x4F01, [char]0x4E1A, [char]0x5FAE, [char]0x4FE1, [char]0x9500, [char]0x552E, [char]0x63A8, [char]0x9001)
$deliveryExe = Join-Path $dist ($deliveryName + ".exe")
Copy-Item -LiteralPath $sourceExe -Destination $deliveryExe -Force
Write-Output $deliveryExe
