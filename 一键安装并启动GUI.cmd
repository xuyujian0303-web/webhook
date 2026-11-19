@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "LOG=%CD%\setup.log"
>"%LOG%" echo Webhook GUI setup started: %date% %time%

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
set "VENV_VALID="
set "INSTALL_REQUIRED="
if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" -c "import sys; assert sys.version_info >= (3, 12)" >nul 2>nul
    if not errorlevel 1 (
        set "VENV_VALID=1"
        "%PYTHON_EXE%" -c "import wecom_sales_webhook_bot, apscheduler, jinja2, pyodbc, requests, sqlalchemy, yaml, PIL, pptx, win32com.client, PyInstaller" >nul 2>nul
        if errorlevel 1 set "INSTALL_REQUIRED=1"
    )
)
if defined VENV_VALID if not defined INSTALL_REQUIRED goto :prepare_runtime

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

echo Creating or repairing project environment...
if exist ".venv\pyvenv.cfg" (
    %BOOTSTRAP_PYTHON% -m venv --clear .venv >>"%LOG%" 2>&1
) else (
    %BOOTSTRAP_PYTHON% -m venv .venv >>"%LOG%" 2>&1
)
if errorlevel 1 goto :show_failure
if not exist "%PYTHON_EXE%" goto :show_failure
"%PYTHON_EXE%" -c "import sys; assert sys.version_info >= (3, 12)" >>"%LOG%" 2>&1
if errorlevel 1 goto :show_failure

:install_dependencies
echo Installing project dependencies...
"%PYTHON_EXE%" -m pip install --upgrade pip >>"%LOG%" 2>&1
if errorlevel 1 goto :show_failure
"%PYTHON_EXE%" -m pip install -e ".[build]" >>"%LOG%" 2>&1
if errorlevel 1 goto :show_failure

:prepare_runtime
if not exist "config.local.yaml" copy /Y "config.example.yaml" "config.local.yaml" >>"%LOG%" 2>&1
if errorlevel 1 goto :show_failure
if not exist "ems_config.json" copy /Y "ems_config.example.json" "ems_config.json" >>"%LOG%" 2>&1
if errorlevel 1 goto :show_failure
if not exist "var" mkdir "var" >>"%LOG%" 2>&1

echo Building the standalone desktop application...
"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean "企业微信销售推送.spec" >>"%LOG%" 2>&1
if errorlevel 1 goto :start_python_gui
if not exist "dist\企业微信销售推送.exe" goto :show_failure
copy /Y "dist\企业微信销售推送.exe" "%CD%\企业微信销售推送.exe" >>"%LOG%" 2>&1
if errorlevel 1 goto :show_failure

echo Starting the desktop application...
start "WeCom Sales GUI" "%CD%\企业微信销售推送.exe"
if errorlevel 1 goto :show_failure
exit /b 0

:start_python_gui
echo EXE build failed. Starting the GUI from the installed Python environment...
set "PYTHONPATH=%CD%\src"
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
