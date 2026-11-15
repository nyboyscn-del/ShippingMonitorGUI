@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found. Please install Python and add it to PATH.
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)

python tools\check_dependencies.py
if errorlevel 1 (
    echo [ERROR] Dependency check failed.
    if not "%AUTO_MODE%"=="1" pause
    exit /b 1
)

python src\gui_main.py
if not "%AUTO_MODE%"=="1" pause
endlocal
