@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON="
where py >nul 2>nul
if not errorlevel 1 (
    py -3.12 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON=py -3.12"
)
if not defined PYTHON (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON=python"
)

if not defined PYTHON (
    echo Python 3.12 was not found. Trying to install it with winget...
    where winget >nul 2>nul
    if errorlevel 1 (
        echo winget is not available. Install Python 3.12 from https://www.python.org/downloads/windows/ and run this file again.
        pause
        exit /b 1
    )
    winget install --id Python.Python.3.12 --exact --scope user --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo Python installation failed.
        pause
        exit /b 1
    )
    set "PATH=%LocalAppData%\Programs\Python\Python312;%LocalAppData%\Programs\Python\Python312\Scripts;%PATH%"
    set "PYTHON=python"
)

echo Installing project dependencies...
%PYTHON% -m pip install --upgrade pip
if errorlevel 1 goto :failed
%PYTHON% -m pip install -e ".[dev]"
if errorlevel 1 goto :failed

if not exist "config.local.yaml" copy /Y "config.example.yaml" "config.local.yaml" >nul
if not exist "ems_config.json" copy /Y "ems_config.example.json" "ems_config.json" >nul
if not exist "var" mkdir "var"

set "PYTHONPATH=%CD%\src"
echo Starting the desktop GUI...
start "WeCom Sales GUI" pythonw.exe -m wecom_sales_webhook_bot.cli desktop-gui --config "%CD%\config.local.yaml"
exit /b 0

:failed
echo Setup failed. Please check the messages above.
pause
exit /b 1