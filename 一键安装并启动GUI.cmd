@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "LOG=%CD%\setup.log"
>"%LOG%" echo Webhook GUI setup started: %date% %time%

set "BOOTSTRAP_PYTHON="
where py >nul 2>nul
if not errorlevel 1 (
    rem Use the newest installed Python 3.x runtime. The project requires 3.12 or newer.
    py -3 -c "import sys; assert sys.version_info >= (3, 12)" >nul 2>nul
    if not errorlevel 1 set "BOOTSTRAP_PYTHON=py -3"
)
if not defined BOOTSTRAP_PYTHON (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys; assert sys.version_info >= (3, 12)" >nul 2>nul
        if not errorlevel 1 set "BOOTSTRAP_PYTHON=python"
    )
)

if not defined BOOTSTRAP_PYTHON (
    echo Python 3.12 or newer was not found. Trying to install it with winget...
    where winget >nul 2>nul
    if errorlevel 1 goto :no_python
    winget install --id Python.Python.3.12 --exact --scope user --accept-package-agreements --accept-source-agreements >>"%LOG%" 2>&1
    if errorlevel 1 goto :show_failure
    set "PATH=%LocalAppData%\Programs\Python\Python312;%LocalAppData%\Programs\Python\Python312\Scripts;%PATH%"
    set "BOOTSTRAP_PYTHON=python"
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating project environment...
    %BOOTSTRAP_PYTHON% -m venv .venv >>"%LOG%" 2>&1
    if errorlevel 1 goto :show_failure
)
set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" goto :show_failure

echo Installing project dependencies...
"%PYTHON_EXE%" -m pip install --upgrade pip >>"%LOG%" 2>&1
if errorlevel 1 goto :show_failure
"%PYTHON_EXE%" -m pip install -e . >>"%LOG%" 2>&1
if errorlevel 1 goto :show_failure

if not exist "config.local.yaml" copy /Y "config.example.yaml" "config.local.yaml" >>"%LOG%" 2>&1
if errorlevel 1 goto :show_failure
if not exist "ems_config.json" copy /Y "ems_config.example.json" "ems_config.json" >>"%LOG%" 2>&1
if errorlevel 1 goto :show_failure
if not exist "var" mkdir "var" >>"%LOG%" 2>&1

set "PYTHONPATH=%CD%\src"
echo Starting the desktop GUI...
start "WeCom Sales GUI" "%PYTHON_EXE:\python.exe=\pythonw.exe%" -m wecom_sales_webhook_bot.cli desktop-gui --config "%CD%\config.local.yaml"
if errorlevel 1 goto :show_failure
exit /b 0

:no_python
echo Python 3.12 or newer was not found, and winget is unavailable.
echo Install Python 3.12 or newer from https://www.python.org/downloads/windows/
echo Make sure "Add Python to PATH" is selected, then run this file again.
goto :show_failure

:show_failure
echo.
echo Setup failed. Details are in:
echo %LOG%
if exist "%LOG%" type "%LOG%"
pause
exit /b 1
