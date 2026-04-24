@echo off
chcp 65001 > nul
REM ===========================================================
REM  Taiwan Industry Map - Daily Auto Rebuild
REM
REM  What it does:
REM    1) Pull latest price/volume/institutional data from FinLab
REM    2) Recompute group metrics, heatmap, stock pages, highlights
REM    3) Rebuild all HTML under site/dist/
REM    4) Log to logs/build_YYYYMMDD_HHMM.log
REM
REM  Suggested cron: daily 14:30 (30min after market close)
REM ===========================================================
setlocal enabledelayedexpansion

REM %~dp0 = directory of this bat (with trailing backslash) - codepage-safe
set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
set "PYTHON=C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe"
set "BUILD_SCRIPT=site\build_site.py"

REM --- Timestamp YYYYMMDD_HHMM (locale-independent via WMIC) ---
for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value 2^>nul ^| find "="') do set "DT=%%a"
set "TIMESTAMP=!DT:~0,8!_!DT:~8,4!"

cd /d "%PROJECT_DIR%"
if errorlevel 1 (
    echo [ERROR] Cannot cd to %PROJECT_DIR%
    pause
    exit /b 1
)

if not exist "logs\" mkdir logs

set "LOG_FILE=logs\build_!TIMESTAMP!.log"

echo ===========================================================
echo  Taiwan Industry Map - Daily Rebuild
echo  Start: %date% %time%
echo  Log:   %LOG_FILE%
echo ===========================================================
echo.

REM --- Run build script, capture stdout+stderr to log ---
"%PYTHON%" "%BUILD_SCRIPT%" > "%LOG_FILE%" 2>&1
set "BUILD_RC=%errorlevel%"

type "%LOG_FILE%"
echo.

if %BUILD_RC% equ 0 (
    echo -----------------------------------------------------------
    echo [OK] Build completed - %date% %time%
    echo   Output: %PROJECT_DIR%\site\dist\
    echo   Log:    %LOG_FILE%
    echo -----------------------------------------------------------
) else (
    echo -----------------------------------------------------------
    echo [FAIL] Build failed, exit code: %BUILD_RC%
    echo   Check log: %LOG_FILE%
    echo -----------------------------------------------------------
)

REM --- Purge logs older than 30 days ---
forfiles /p "logs" /s /m *.log /d -30 /c "cmd /c del @file" 2>nul

REM ===========================================================
REM  Auto-deploy to Cloudflare Pages via Git
REM  Only runs when build succeeded AND git is initialized
REM  Set DEPLOY=0 at top to disable
REM ===========================================================
set "DEPLOY=1"

if %BUILD_RC% neq 0 (
    echo [SKIP] Build failed, skipping deploy
    goto :END
)
if "%DEPLOY%"=="0" goto :END

where git >nul 2>&1
if errorlevel 1 (
    echo [SKIP] git not found, skipping deploy
    goto :END
)

if not exist ".git\" (
    echo [SKIP] Not a git repo, run: git init  first
    goto :END
)

REM --- Check if there is anything to commit ---
git diff --quiet --exit-code 2>nul
set "HAS_CHANGES=%errorlevel%"
git diff --cached --quiet --exit-code 2>nul
if errorlevel 1 set "HAS_CHANGES=1"

git status --porcelain 2>nul | findstr /r "." >nul
if not errorlevel 1 set "HAS_CHANGES=1"

if "%HAS_CHANGES%"=="0" (
    echo [INFO] No changes to deploy
    goto :END
)

echo.
echo -----------------------------------------------------------
echo [DEPLOY] Auto commit and push to origin...
echo -----------------------------------------------------------
git add -A
git commit -m "auto rebuild %TIMESTAMP%" --quiet
git push origin HEAD --quiet
if errorlevel 1 (
    echo [WARN] git push failed - check remote / network
) else (
    echo [OK] Pushed, Cloudflare Pages will redeploy
)

:END
REM --- Keep window open if run interactively, close if scheduled ---
if /i "%1" neq "quiet" (
    echo.
    echo Press any key to close...
    pause > nul
)

exit /b %BUILD_RC%
