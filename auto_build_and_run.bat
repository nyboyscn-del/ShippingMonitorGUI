@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "tools" mkdir "tools"
if not exist "tools\logs" mkdir "tools\logs"

set "LOG_DIR=tools\logs"
set "LOG_FILE=%LOG_DIR%\auto_build_and_run.log"
set "EXE_RELATIVE=dist\ShippingMonitorGUI\ShippingMonitorGUI.exe"
set "EXE_PATH=%CD%\%EXE_RELATIVE%"
set "FALLBACK_TARGET=D:\AI_Projects\99_Temp\ShippingMonitorGUI_USB_Test"
if "%USB_TARGET_DIR%"=="" call :detect_usb_target

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH:mm:ss"') do set "RUN_TS=%%I"

> "%LOG_FILE%" echo ========================================================
>> "%LOG_FILE%" echo ShippingMonitorGUI final user USB automation
>> "%LOG_FILE%" echo Project: %CD%
>> "%LOG_FILE%" echo Started: %RUN_TS%
>> "%LOG_FILE%" echo ========================================================

echo.
echo ================================================
call :say "U2hpcHBpbmdNb25pdG9yR1VJIFVTQiDkvr/mkLrniYjlkK/liqjnqIvluo8="
echo ================================================
echo.

call :say "5byA5aeL5omn6KGMIFNoaXBwaW5nTW9uaXRvckdVSSBVU0Ig5L6/5pC654mI6Ieq5Yqo5YyW5rWB56iL44CC"
call :log "Starting ShippingMonitorGUI USB automation."
call :log "Log file: %LOG_FILE%"
call :log "USB target folder: %USB_TARGET_DIR%"

where python >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :fail "Python was not found. Please install Python 3.10+ and add it to PATH."
    exit /b 1
)

call :say "5q2j5Zyo5qOA5p+lIFB5dGhvbuOAgeS+nei1luW6k+WSjCBGRm1wZWcuLi4="
python tools\check_dependencies.py >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :fail "Dependency check failed. Review the log file."
    exit /b 1
)
call :say "5L6d6LWW5qOA5rWL5a6M5oiQ44CC"
call :log "Dependency check completed."

call :prepare_usb_package
if errorlevel 1 exit /b 1

if not exist "%EXE_PATH%" (
    call :fail "EXE was not found: %EXE_PATH%"
    exit /b 1
)

call :say "5q2j5Zyo5ZCv5YqoIFNoaXBwaW5nTW9uaXRvckdVSe+8jOivt+eojeWAmS4uLg=="
call :log "Starting EXE: %EXE_PATH%"
start "" "%EXE_PATH%"

call :log "EXE start command completed."
echo.
call :say "W+WujOaIkF0gU2hpcHBpbmdNb25pdG9yR1VJIOW3suWQr+WKqOOAgg=="
call :say "5pel5b+X5paH5Lu277ya"
echo %LOG_FILE%
if not "%AUTO_MODE%"=="1" pause
exit /b 0

:detect_usb_target
set "USB_DRIVE="
for %%D in (D E F G H I J K L M N O P Q R S T U V W X Y Z) do if not defined USB_DRIVE call :check_drive %%D
if "%USB_DRIVE%"=="" (
    set "USB_TARGET_DIR=%FALLBACK_TARGET%"
    exit /b 0
)
set "USB_TARGET_DIR=%USB_DRIVE%\ShippingMonitorGUI_USB"
exit /b 0

:check_drive
powershell -NoProfile -Command "$d='%~1'; $v=Get-Volume -DriveLetter $d -ErrorAction SilentlyContinue; if($v -and $v.DriveType -eq 'Removable'){exit 0}else{exit 1}" >nul 2>nul
if not errorlevel 1 set "USB_DRIVE=%~1:"
exit /b 0

:prepare_usb_package
call :say "5q2j5Zyo5pW055CGIFVTQiDmlofku7YuLi4="
call :log "Preparing USB package: %USB_TARGET_DIR%"

if not exist "%USB_TARGET_DIR%" mkdir "%USB_TARGET_DIR%" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :fail "Could not create USB target folder: %USB_TARGET_DIR%"
    exit /b 1
)

call :copy_file "auto_build_and_run.bat" "%USB_TARGET_DIR%\auto_build_and_run.bat"
if errorlevel 1 exit /b 1
call :copy_file "package_usb_final_codex.bat" "%USB_TARGET_DIR%\package_usb_final_codex.bat"
if errorlevel 1 exit /b 1
call :copy_file "build_exe.bat" "%USB_TARGET_DIR%\build_exe.bat"
if errorlevel 1 exit /b 1
call :copy_file "run_gui_stage1.bat" "%USB_TARGET_DIR%\run_gui_stage1.bat"
if errorlevel 1 exit /b 1

call :copy_dir "config" "%USB_TARGET_DIR%\config"
if errorlevel 1 exit /b 1
call :copy_dir "data" "%USB_TARGET_DIR%\data"
if errorlevel 1 exit /b 1
call :copy_dir "logs" "%USB_TARGET_DIR%\logs"
if errorlevel 1 exit /b 1
call :copy_dir "reports" "%USB_TARGET_DIR%\reports"
if errorlevel 1 exit /b 1
call :copy_dir "tools" "%USB_TARGET_DIR%\tools"
if errorlevel 1 exit /b 1
call :copy_dir "src" "%USB_TARGET_DIR%\src"
if errorlevel 1 exit /b 1
call :copy_dir "dist" "%USB_TARGET_DIR%\dist"
if errorlevel 1 exit /b 1

if not exist "%USB_TARGET_DIR%\config\config.json" (
    call :fail "USB package is missing config\config.json."
    exit /b 1
)
if not exist "%USB_TARGET_DIR%\config\config.example.json" (
    call :fail "USB package is missing config\config.example.json."
    exit /b 1
)
if not exist "%USB_TARGET_DIR%\config\license.json" (
    call :fail "USB package is missing config\license.json."
    exit /b 1
)
if not exist "%USB_TARGET_DIR%\%EXE_RELATIVE%" (
    call :fail "USB package is missing %EXE_RELATIVE%."
    exit /b 1
)

call :say "VVNCIOaWh+S7tuaVtOeQhuWujOaIkOOAgg=="
call :log "USB package prepared: %USB_TARGET_DIR%"
exit /b 0

:copy_file
if not exist "%~1" (
    call :fail "Required file was not found: %~1"
    exit /b 1
)
copy /Y "%~1" "%~2" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :fail "Failed to copy file: %~1"
    exit /b 1
)
exit /b 0

:copy_dir
if not exist "%~1" (
    mkdir "%~2" >> "%LOG_FILE%" 2>&1
    call :log "Source folder missing; created empty target folder for: %~1"
    exit /b 0
)
robocopy "%~1" "%~2" /E /NFL /NDL /NJH /NJS /NC /NS >> "%LOG_FILE%" 2>&1
if errorlevel 8 (
    call :fail "Failed to copy folder: %~1"
    exit /b 1
)
exit /b 0

:log
echo [INFO] %~1
>> "%LOG_FILE%" echo [INFO] %~1
exit /b 0

:fail
call :say "W+mUmeivr10g5omn6KGM5aSx6LSl77yM6K+35p+l55yL5pel5b+X5paH5Lu277ya"
echo %~1
echo %LOG_FILE%
>> "%LOG_FILE%" echo [ERROR] %~1
if not "%AUTO_MODE%"=="1" pause
exit /b 1

:say
powershell -NoProfile -Command "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Write-Host ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%~1')))"
exit /b 0
