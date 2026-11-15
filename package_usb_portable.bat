@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if "%USB_TARGET_DIR%"=="" set "USB_TARGET_DIR=E:\ShippingMonitorGUI_USB"

if not exist "tools\logs" mkdir "tools\logs"

echo [INFO] ShippingMonitorGUI USB portable package automation
echo [INFO] Project: %CD%
echo [INFO] USB target: %USB_TARGET_DIR%
echo.

python tools\package_usb_portable.py --target "%USB_TARGET_DIR%" --build --start
if errorlevel 1 (
    echo.
    echo [ERROR] USB portable package automation failed.
    echo [INFO] See tools\logs\auto_build_and_run.log
    pause
    exit /b 1
)

echo.
echo [OK] USB portable package automation completed.
echo [INFO] See tools\logs\auto_build_and_run.log
pause
exit /b 0
