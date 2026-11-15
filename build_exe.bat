@echo off
setlocal

REM =========================================================
REM ShippingMonitorGUI build script (Python -m PyInstaller version)
REM Project root: the directory containing this script
REM Expected files:
REM   src\gui_main.py
REM   config\config.json
REM   config\config.example.json
REM =========================================================

cd /d "%~dp0"

REM Check and install Python dependencies for the current user.
python tools\check_dependencies.py
if errorlevel 1 (
    echo [ERROR] Dependency check failed.
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)

REM Check that the config folder exists before packaging.
if not exist "config" (
    echo [ERROR] config directory was not found.
    echo Make sure config contains config.json and config.example.json.
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)
if not exist "web\lan_query\index.html" (
    echo [ERROR] Missing web\lan_query\index.html
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)
if not exist "web\lan_query\style.css" (
    echo [ERROR] Missing web\lan_query\style.css
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)
if not exist "web\lan_query\app.js" (
    echo [ERROR] Missing web\lan_query\app.js
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)

REM Check PyInstaller before deleting build outputs.
python -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] PyInstaller was not found in the current Python environment.
    echo Install it first with:
    echo   python -m pip install pyinstaller
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)

echo [ShippingMonitorGUI] Cleaning previous build/dist folders...
REM Remove known state-file variants before deleting old output.
if exist "dist\ShippingMonitorGUI" (
    for /r "dist\ShippingMonitorGUI" %%F in (license.json license_state* trial_state* *.bak_test *.tmp *.old) do (
        if exist "%%F" del /q "%%F" >nul 2>nul
    )
)
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

echo [ShippingMonitorGUI] Preparing output folder...
if not exist "dist" mkdir "dist"

REM =========================================================
REM Build the application with PyInstaller via Python module
REM =========================================================
echo [ShippingMonitorGUI] Building EXE...
set "ASSETS_ADD_DATA="
if exist "src\assets" set ASSETS_ADD_DATA=--add-data "src\assets;assets"
set "FFMPEG_ADD_DATA="
if exist "tools\ffmpeg\ffmpeg.exe" set FFMPEG_ADD_DATA=--add-data "tools\ffmpeg;tools\ffmpeg"
if exist "tools\ffmpeg\bin\ffmpeg.exe" set FFMPEG_ADD_DATA=--add-data "tools\ffmpeg;tools\ffmpeg"
set "PYQT5_SIP_ADD_BINARY="
for /f "delims=" %%I in ('python -c "import PyQt5.sip as sip; print(sip.__file__)"') do set "PYQT5_SIP_ADD_BINARY=--add-binary ""%%I;PyQt5"""

python -m PyInstaller ^
    src\gui_main.py ^
    --name ShippingMonitorGUI ^
    --onedir ^
    --noconsole ^
    --add-data "config;config" ^
    --add-data "web;web" ^
    --add-data "templates;templates" ^
    %ASSETS_ADD_DATA% ^
    %FFMPEG_ADD_DATA% ^
    %PYQT5_SIP_ADD_BINARY% ^
    --paths src ^
    --hidden-import query_manager ^
    --hidden-import playback_manager ^
    --distpath dist ^
    --workpath build ^
    --clean ^
    --noconfirm

if errorlevel 1 (
    echo [ERROR] Build failed.
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)

set "APP_DIR=dist\ShippingMonitorGUI"
set "APP_CONFIG_DIR=%APP_DIR%\config"

REM Create runtime folders next to the EXE.
echo [ShippingMonitorGUI] Preparing runtime folders...
if not exist "%APP_DIR%" (
    echo [ERROR] Expected EXE output folder was not found: %APP_DIR%
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)
if not exist "%APP_CONFIG_DIR%" mkdir "%APP_CONFIG_DIR%"
if not exist "%APP_DIR%\reports" mkdir "%APP_DIR%\reports"

REM Copy config files to the EXE folder explicitly.
echo [ShippingMonitorGUI] Copying config folder to EXE output...
xcopy "config\*" "%APP_CONFIG_DIR%\" /E /I /Y >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy config files.
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)
REM A clean source checkout tracks only the example config. Seed the package
REM default from that template without writing a machine-specific config back
REM into the source tree.
if not exist "%APP_CONFIG_DIR%\config.json" (
    copy /y "%APP_CONFIG_DIR%\config.example.json" "%APP_CONFIG_DIR%\config.json" >nul
    if errorlevel 1 (
        echo [ERROR] Failed to create packaged config.json from the example.
        if not "%AUTO_MODE%"=="1" pause
        exit /b 1
    )
)

REM Copy LAN query static files next to the EXE because runtime_root() resolves there.
echo [ShippingMonitorGUI] Copying LAN query web files to EXE output...
if exist "%APP_DIR%\web" rmdir /s /q "%APP_DIR%\web"
xcopy "web\*" "%APP_DIR%\web\" /E /I /Y >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy LAN query web files.
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)

REM Customer EXE output must not include legacy or local activation state files.
if exist "%APP_DIR%\license.json" del /q "%APP_DIR%\license.json" >nul 2>nul
if exist "%APP_DIR%\license_state.json" del /q "%APP_DIR%\license_state.json" >nul 2>nul
if exist "%APP_DIR%\license_state*.json" del /q "%APP_DIR%\license_state*.json" >nul 2>nul
if exist "%APP_DIR%\trial_state.json" del /q "%APP_DIR%\trial_state.json" >nul 2>nul
if exist "%APP_DIR%\trial_state*.json" del /q "%APP_DIR%\trial_state*.json" >nul 2>nul
if exist "%APP_CONFIG_DIR%\license.json" del /q "%APP_CONFIG_DIR%\license.json" >nul 2>nul
if exist "%APP_CONFIG_DIR%\license_state.json" del /q "%APP_CONFIG_DIR%\license_state.json" >nul 2>nul
if exist "%APP_CONFIG_DIR%\license_state*.json" del /q "%APP_CONFIG_DIR%\license_state*.json" >nul 2>nul
if exist "%APP_CONFIG_DIR%\trial_state.json" del /q "%APP_CONFIG_DIR%\trial_state.json" >nul 2>nul
if exist "%APP_CONFIG_DIR%\trial_state*.json" del /q "%APP_CONFIG_DIR%\trial_state*.json" >nul 2>nul
if exist "%APP_DIR%\_internal\config\license.json" del /q "%APP_DIR%\_internal\config\license.json" >nul 2>nul
if exist "%APP_DIR%\_internal\config\license_state.json" del /q "%APP_DIR%\_internal\config\license_state.json" >nul 2>nul
if exist "%APP_DIR%\_internal\config\license_state*.json" del /q "%APP_DIR%\_internal\config\license_state*.json" >nul 2>nul
if exist "%APP_DIR%\_internal\config\trial_state.json" del /q "%APP_DIR%\_internal\config\trial_state.json" >nul 2>nul
if exist "%APP_DIR%\_internal\config\trial_state*.json" del /q "%APP_DIR%\_internal\config\trial_state*.json" >nul 2>nul

REM Remove runtime-generated folders and supplier-only artifacts from customer output.
for %%D in (evidence_packages data recordings logs backup) do (
    if exist "%APP_DIR%\%%D" rmdir /s /q "%APP_DIR%\%%D"
    if exist "%APP_DIR%\_internal\%%D" rmdir /s /q "%APP_DIR%\_internal\%%D"
)
if exist "%APP_DIR%\tools\license_keys" rmdir /s /q "%APP_DIR%\tools\license_keys"
if exist "%APP_DIR%\_internal\tools\license_keys" rmdir /s /q "%APP_DIR%\_internal\tools\license_keys"
for /r "%APP_DIR%" %%F in (license.json license_state* trial_state* *.bak_test *.tmp *.old license_code_generator.py issued_licenses.csv *.pem) do (
    if exist "%%F" del /q "%%F" >nul 2>nul
)

REM Sanitize only packaged config files. Never modify the project runtime config.
python -c "import json; from pathlib import Path; files=[Path(r'%APP_CONFIG_DIR%\config.json'),Path(r'%APP_DIR%\_internal\config\config.json')]; [(lambda d,p:(d.__setitem__('lan_query_token',''),p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')))(json.loads(p.read_text(encoding='utf-8')),p) for p in files if p.exists()]"
if errorlevel 1 (
    echo [ERROR] Failed to sanitize lan_query_token in packaged config.
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)

REM Verify required config files after copy.
if not exist "%APP_CONFIG_DIR%\config.json" (
    echo [ERROR] Missing %APP_CONFIG_DIR%\config.json
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)
if not exist "%APP_CONFIG_DIR%\config.example.json" (
    echo [ERROR] Missing %APP_CONFIG_DIR%\config.example.json
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)
if not exist "%APP_DIR%\web\lan_query\index.html" (
    echo [ERROR] Missing %APP_DIR%\web\lan_query\index.html
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)
if not exist "%APP_DIR%\web\lan_query\style.css" (
    echo [ERROR] Missing %APP_DIR%\web\lan_query\style.css
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)
if not exist "%APP_DIR%\web\lan_query\app.js" (
    echo [ERROR] Missing %APP_DIR%\web\lan_query\app.js
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)
REM Confirm supplier-only license keys and tools are absent from the customer output.
echo [ShippingMonitorGUI] Checking release output for license secrets...
python tools\check_release_security.py --root "%APP_DIR%"
if errorlevel 1 (
    echo [ERROR] Release security check failed.
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)

REM =========================================================
echo [ShippingMonitorGUI] Build finished.
echo EXE output folder: dist\ShippingMonitorGUI
echo Check dist\ShippingMonitorGUI for ShippingMonitorGUI.exe and the config folder.
if not "%AUTO_MODE%"=="1" pause
