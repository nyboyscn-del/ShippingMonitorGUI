@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Please install Python and add it to PATH.
    exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency installation failed.
    exit /b 1
)

python src\main.py
endlocal
