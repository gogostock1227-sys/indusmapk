@echo off
chcp 65001 > nul
REM ===========================================================
REM  Taiwan Industry Map - Weekly (Saturday) Deep Rebuild
REM
REM  What it does:
REM    Step 1/2: fetch_holders_history.py --weeks 4
REM              -> 回補 TDCC 集保分級歷史 4 週（per-stock x per-week）
REM    Step 2/2: call daily_build.bat quiet
REM              -> 正常每日流程（extras + rich + build + push）
REM
REM  Suggested cron: Saturday 15:00
REM  TDCC 集保週報週五晚間發佈，週六跑剛好
REM ===========================================================
setlocal enabledelayedexpansion

REM %~dp0 = directory of this bat (with trailing backslash)
set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
set "PYTHON=C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe"

REM --- Timestamp YYYYMMDD_HHMM ---
for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value 2^>nul ^| find "="') do set "DT=%%a"
set "TIMESTAMP=!DT:~0,8!_!DT:~8,4!"

cd /d "%PROJECT_DIR%"
if errorlevel 1 (
    echo [ERROR] Cannot cd to %PROJECT_DIR%
    pause
    exit /b 1
)

if not exist "logs\" mkdir logs
set "LOG_FILE=logs\weekly_!TIMESTAMP!.log"

echo ===========================================================
echo  Weekly Rebuild - Saturday deep refresh
echo  Start: %date% %time%
echo  Log:   %LOG_FILE%
echo ===========================================================
echo.

REM --- Step 1/2: 回補集保分級歷史 4 週 ---
echo === [Weekly Step 1/2] fetch_holders_history.py --weeks 4 === > "%LOG_FILE%"
echo Start: %date% %time% >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"
"%PYTHON%" "site\fetch_holders_history.py" --weeks 4 >> "%LOG_FILE%" 2>&1
set "HIST_RC=%errorlevel%"
if not "%HIST_RC%"=="0" (
    echo [WARN] fetch_holders_history exit %HIST_RC%, continue to daily build anyway >> "%LOG_FILE%"
)

REM --- Step 2/2: 轉交 daily_build.bat 做標準流程 ---
echo. >> "%LOG_FILE%"
echo === [Weekly Step 2/2] Invoke daily_build.bat === >> "%LOG_FILE%"
echo Start: %date% %time% >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

REM call 才能拿到 daily_build 的 errorlevel 回來
call "%PROJECT_DIR%\daily_build.bat" quiet
set "DAILY_RC=%errorlevel%"

echo.
if %DAILY_RC% equ 0 (
    echo -----------------------------------------------------------
    echo [OK] Weekly rebuild completed - %date% %time%
    echo   History backfill RC: %HIST_RC%
    echo   Daily build RC:      %DAILY_RC%
    echo -----------------------------------------------------------
) else (
    echo -----------------------------------------------------------
    echo [FAIL] Weekly rebuild daily step failed, RC=%DAILY_RC%
    echo   Check logs: %LOG_FILE%
    echo -----------------------------------------------------------
)

REM --- 清 90 天前的 weekly log ---
forfiles /p "logs" /s /m weekly_*.log /d -90 /c "cmd /c del @file" 2>nul

REM --- Keep window open if run interactively, close if scheduled ---
if /i "%1" neq "quiet" (
    echo.
    echo Press any key to close...
    pause > nul
)

exit /b %DAILY_RC%
