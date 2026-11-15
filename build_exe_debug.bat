@echo off
setlocal

REM =========================================================
REM ShippingMonitorGUI debug build script with console output
REM Project root: D:\AI_Projects\shipping-monitor-gui-final
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
    echo Make sure config contains config.json, config.example.json, and license.json.
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)

REM Check PyInstaller before deleting debug build outputs.
python -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] PyInstaller was not found in the current Python environment.
    echo Install it first with:
    echo   python -m pip install pyinstaller
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)

echo [ShippingMonitorGUI Debug] Cleaning previous debug output...
if exist "build_debug" rmdir /s /q "build_debug"
if exist "dist\ShippingMonitorGUI_Debug" rmdir /s /q "dist\ShippingMonitorGUI_Debug"
if not exist "dist" mkdir "dist"

REM Build the debug application with PyInstaller console output enabled.
echo [ShippingMonitorGUI Debug] Building console EXE...
set "ASSETS_ADD_DATA="
if exist "src\assets" set ASSETS_ADD_DATA=--add-data "src\assets;assets"
set "FFMPEG_ADD_DATA="
if exist "tools\ffmpeg\ffmpeg.exe" set FFMPEG_ADD_DATA=--add-data "tools\ffmpeg;tools\ffmpeg"
if exist "tools\ffmpeg\bin\ffmpeg.exe" set FFMPEG_ADD_DATA=--add-data "tools\ffmpeg;tools\ffmpeg"
set "PYQT5_SIP_ADD_BINARY="
for /f "delims=" %%I in ('python -c "import PyQt5.sip as sip; print(sip.__file__)"') do set "PYQT5_SIP_ADD_BINARY=--add-binary ""%%I;PyQt5"""

python -m PyInstaller ^
    src\gui_main.py ^
    --name ShippingMonitorGUI_Debug ^
    --onedir ^
    --add-data "config;config" ^
    %ASSETS_ADD_DATA% ^
    %FFMPEG_ADD_DATA% ^
    %PYQT5_SIP_ADD_BINARY% ^
    --paths src ^
    --paths "C:\Users\nyboy\AppData\Roaming\Python\Python314\site-packages" ^
    --hidden-import query_manager ^
    --hidden-import playback_manager ^
    --distpath dist ^
    --workpath build_debug ^
    --clean ^
    --noconfirm

if errorlevel 1 (
    echo [ERROR] Debug build failed.
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)

set "APP_DIR=dist\ShippingMonitorGUI_Debug"
set "APP_CONFIG_DIR=%APP_DIR%\config"

REM Create runtime folders next to the debug EXE.
echo [ShippingMonitorGUI Debug] Preparing runtime folders...
if not exist "%APP_DIR%" (
    echo [ERROR] Expected debug EXE output folder was not found: %APP_DIR%
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)
if not exist "%APP_CONFIG_DIR%" mkdir "%APP_CONFIG_DIR%"
if not exist "%APP_DIR%\data" mkdir "%APP_DIR%\data"
if not exist "%APP_DIR%\logs" mkdir "%APP_DIR%\logs"
if not exist "%APP_DIR%\reports" mkdir "%APP_DIR%\reports"

REM Copy config files to the debug EXE folder explicitly.
echo [ShippingMonitorGUI Debug] Copying config folder to debug output...
xcopy "config\*" "%APP_CONFIG_DIR%\" /E /I /Y >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy config files.
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)

REM Debug output must not inherit local activation state from the build machine.
if exist "%APP_CONFIG_DIR%\license_state*" del /q "%APP_CONFIG_DIR%\license_state*" >nul 2>nul
if exist "%APP_DIR%\_internal\config\license_state*" del /q "%APP_DIR%\_internal\config\license_state*" >nul 2>nul

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
if not exist "%APP_CONFIG_DIR%\license.json" (
    echo [ERROR] Missing %APP_CONFIG_DIR%\license.json
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)

REM Confirm supplier-only license keys and tools are absent from the debug output.
echo [ShippingMonitorGUI Debug] Checking debug output for license secrets...
python tools\check_release_security.py --root "%APP_DIR%"
if errorlevel 1 (
    echo [ERROR] Debug output security check failed.
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)

echo [ShippingMonitorGUI Debug] Build finished.
echo Debug EXE output folder: dist\ShippingMonitorGUI_Debug
echo Run dist\ShippingMonitorGUI_Debug\ShippingMonitorGUI_Debug.exe for console output.
if not "%AUTO_MODE%"=="1" pause
