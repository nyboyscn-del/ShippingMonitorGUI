@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

set "LOG_DIR=tools\logs"
set "LOG_FILE=%LOG_DIR%\auto_build_and_run.log"
set "FALLBACK_TARGET=D:\AI_Projects\99_Temp\ShippingMonitorGUI_USB_Test"
set "EXE_RELATIVE=dist\ShippingMonitorGUI\ShippingMonitorGUI.exe"
set "LOCAL_EXE=%CD%\%EXE_RELATIVE%"

if not exist "tools" mkdir "tools"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH:mm:ss"') do set "RUN_TS=%%I"

> "%LOG_FILE%" echo ========================================================
>> "%LOG_FILE%" echo ShippingMonitorGUI USB copy and test automation
>> "%LOG_FILE%" echo Project: %CD%
>> "%LOG_FILE%" echo Started: %RUN_TS%
>> "%LOG_FILE%" echo ========================================================

echo.
echo ================================================
call :say "U2hpcHBpbmdNb25pdG9yR1VJIFVTQiDlpI3liLbkuI7mtYvor5XohJrmnKw="
echo ================================================
echo.

call :say "5byA5aeL5omn6KGMIFVTQiDlpI3liLbkuI7mtYvor5XmtYHnqIvjgII="
call :log "Starting USB copy and test automation."

if "%USB_TARGET_DIR%"=="" (
    call :detect_usb_target
) else (
    call :log "Using preset USB_TARGET_DIR: %USB_TARGET_DIR%"
)

call :log "Target folder: %USB_TARGET_DIR%"

where python >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :fail "Python was not found. Please install Python 3.10+ and add it to PATH."
    exit /b 1
)

call :say "5q2j5Zyo5qOA5rWLIFB5dGhvbuOAgeS+nei1luW6k+WSjCBGRm1wZWcuLi4="
call :log "Checking Python, dependencies, and FFmpeg."
python tools\check_dependencies.py >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :fail "Dependency check failed."
    exit /b 1
)

where ffmpeg >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :say "5pyq5ZyoIFBBVEgg5Lit5qOA5rWL5YiwIEZGbXBlZ++8jOWwhue7p+e7reS9v+eUqCBPcGVuQ1YgTVA0ViDovaznoIHog73lipvjgII="
    call :log "FFmpeg was not found in PATH. OpenCV MP4V conversion remains available."
) else (
    call :say "5bey5ZyoIFBBVEgg5Lit5qOA5rWL5YiwIEZGbXBlZ+OAgg=="
    call :log "FFmpeg was found in PATH."
)

call :say "5q2j5Zyo5p6E5bu6IEVYRe+8jOivt+eojeWAmS4uLg=="
call :log "Building EXE with build_exe.bat."
set "AUTO_MODE=1"
call build_exe.bat >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :fail "EXE build failed."
    exit /b 1
)

if not exist "%LOCAL_EXE%" (
    call :fail "Build finished but EXE was not found: %LOCAL_EXE%"
    exit /b 1
)
call :say "RVhFIOaehOW7uuWujOaIkOOAgg=="
call :log "EXE build completed: %LOCAL_EXE%"

call :prepare_usb_package
if errorlevel 1 exit /b 1

set "FINAL_EXE=%USB_TARGET_DIR%\%EXE_RELATIVE%"
if not exist "%FINAL_EXE%" (
    call :fail "Target EXE was not found: %FINAL_EXE%"
    exit /b 1
)

call :say "5q2j5Zyo5ZCv5YqoIEVYRe+8jOivt+eojeWAmS4uLg=="
call :log "Starting target EXE: %FINAL_EXE%"
start "" "%FINAL_EXE%"

call :say "5rWB56iL5a6M5oiQ44CC"
call :log "Process completed."
call :say "6L6T5Ye655uu5b2V77ya"
echo %USB_TARGET_DIR%
call :say "5pel5b+X5paH5Lu277ya"
echo %LOG_FILE%
if not "%AUTO_MODE%"=="1" pause
exit /b 0

:detect_usb_target
set "USB_DRIVE="
for %%D in (D E F G H I J K L M N O P Q R S T U V W X Y Z) do if not defined USB_DRIVE call :check_drive %%D
if "%USB_DRIVE%"=="" (
    set "USB_TARGET_DIR=%FALLBACK_TARGET%"
    call :say "5pyq5qOA5rWL5YiwIFUg55uY77yM5L2/55So5pys5Zyw5Li05pe255uu5b2V44CC"
    call :log "No removable USB drive detected. Using fallback folder: %FALLBACK_TARGET%"
    exit /b 0
)
set "USB_TARGET_DIR=%USB_DRIVE%\ShippingMonitorGUI_USB"
call :say "5qOA5rWL5YiwIFUg55uY55uY56ym44CC"
echo %USB_DRIVE%
call :log "USB drive detected: %USB_DRIVE%"
exit /b 0

:check_drive
powershell -NoProfile -Command "$d='%~1'; $v=Get-Volume -DriveLetter $d -ErrorAction SilentlyContinue; if($v -and $v.DriveType -eq 'Removable'){exit 0}else{exit 1}" >nul 2>nul
if not errorlevel 1 set "USB_DRIVE=%~1:"
exit /b 0

:prepare_usb_package
call :say "5q2j5Zyo5aSN5Yi26aG555uu5paH5Lu25Yiw55uu5qCH55uu5b2VLi4u"
call :log "Preparing target package: %USB_TARGET_DIR%"

if not exist "%USB_TARGET_DIR%" mkdir "%USB_TARGET_DIR%" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :fail "Could not create target folder: %USB_TARGET_DIR%"
    exit /b 1
)

call :copy_file "usb_copy_and_test_codex.bat" "%USB_TARGET_DIR%\usb_copy_and_test_codex.bat"
if errorlevel 1 exit /b 1
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
    call :fail "Target package is missing config\config.json."
    exit /b 1
)
if not exist "%USB_TARGET_DIR%\config\config.example.json" (
    call :fail "Target package is missing config\config.example.json."
    exit /b 1
)
if not exist "%USB_TARGET_DIR%\config\license.json" (
    call :fail "Target package is missing config\license.json."
    exit /b 1
)
if not exist "%USB_TARGET_DIR%\%EXE_RELATIVE%" (
    call :fail "Target package is missing %EXE_RELATIVE%."
    exit /b 1
)

call :say "6aG555uu5paH5Lu25aSN5Yi25a6M5oiQ44CC"
call :say "5YWz6ZSu5paH5Lu25qCh6aqM6YCa6L+H44CC"
call :log "Target package verified: %USB_TARGET_DIR%"
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
