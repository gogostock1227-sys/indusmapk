@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

REM ===========================================================
REM  One-time TDCC holders history backfill (52 official dates)
REM
REM  This is for manual deep backfill only.
REM  weekly_build.bat stays on the faster 4-week incremental flow.
REM ===========================================================

set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
set "PYTHON=C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe"

for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value 2^>nul ^| find "="') do set "DT=%%a"
set "TIMESTAMP=!DT:~0,8!_!DT:~8,4!"

cd /d "%PROJECT_DIR%"
if errorlevel 1 (
    echo [ERROR] Cannot cd to %PROJECT_DIR%
    pause
    exit /b 1
)

if not exist "logs\" mkdir logs
set "LOG_FILE=logs\holders_52w_!TIMESTAMP!.log"

echo ===========================================================
echo  TDCC Holders 52-week Backfill
echo  Start: %date% %time%
echo  Log:   %LOG_FILE%
echo ===========================================================
echo.

echo === [1/2] fetch_holders_history.py --weeks 52 === > "%LOG_FILE%"
echo Start: %date% %time% >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

"%PYTHON%" "site\fetch_holders_history.py" --weeks 52 --symbols-file "site\.holders_backfill_targets.txt" --workers 8 --sleep 0.25 --save-every 500 >> "%LOG_FILE%" 2>&1
set "HIST_RC=%errorlevel%"
if not "%HIST_RC%"=="0" (
    echo [FAIL] 52-week holders backfill failed, RC=%HIST_RC%
    echo Check logs: %LOG_FILE%
    if /i "%1" neq "quiet" pause
    exit /b %HIST_RC%
)

echo. >> "%LOG_FILE%"
echo === [2/2] build_site.py --skip-finlab === >> "%LOG_FILE%"
echo Start: %date% %time% >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

"%PYTHON%" "site\build_site.py" --skip-finlab >> "%LOG_FILE%" 2>&1
set "BUILD_RC=%errorlevel%"

echo.
if "%BUILD_RC%"=="0" (
    echo -----------------------------------------------------------
    echo [OK] 52-week holders backfill completed - %date% %time%
    echo   History backfill RC: %HIST_RC%
    echo   Build RC:            %BUILD_RC%
    echo -----------------------------------------------------------
) else (
    echo -----------------------------------------------------------
    echo [FAIL] Build failed, RC=%BUILD_RC%
    echo   Check logs: %LOG_FILE%
    echo -----------------------------------------------------------
)

if /i "%1" neq "quiet" (
    echo.
    echo Press any key to close...
    pause > nul
)

exit /b %BUILD_RC%
