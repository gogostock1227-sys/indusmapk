@echo off
chcp 65001 > nul
REM ===========================================================
REM  Taiwan Industry Map - Daily Auto Rebuild
REM
REM  Pipeline (3 steps):
REM    Step 1/3: fetch_extras.py       -> extras and TDCC holders
REM    Step 2/3: fetch_company_rich.py -> company rich data
REM    Step 3/3: build_site.py         -> prices/chips/render pages
REM
REM  Limit-up analysis:
REM    Uses latest enriched-*.json reports when available.
REM
REM  Log: logs/build_YYYYMMDD_HHMM.log
REM  Schedule:
REM    daily 15:30  first after-market pass
REM    daily 17:00  main complete pass
REM    daily 21:30  evening completeness pass
REM ===========================================================
setlocal enabledelayedexpansion

REM %~dp0 = directory of this bat (with trailing backslash) - codepage-safe
set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
set "PYTHON=C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe"
set "BUILD_SCRIPT=site\build_site.py"

REM --- Timestamp YYYYMMDD_HHMM (PowerShell; avoids WMIC dependency) ---
for /f %%a in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Date -Format yyyyMMdd_HHmm"') do set "TIMESTAMP=%%a"
if not defined TIMESTAMP set "TIMESTAMP=manual_%RANDOM%"

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

REM --- Step 1/3: fetch extras (disposal + TDCC holders weekly) ---
echo === [Step 1/3] Fetch extras === > "%LOG_FILE%"
echo Start: %date% %time% >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"
"%PYTHON%" "site\fetch_extras.py" >> "%LOG_FILE%" 2>&1
set "EXTRAS_RC=%errorlevel%"
if not "%EXTRAS_RC%"=="0" (
    echo [WARN] fetch_extras exit %EXTRAS_RC%, continue anyway >> "%LOG_FILE%"
)

REM --- Step 2/3: Refresh company rich data (basic/business/revenue/financials/dividends/director) ---
echo. >> "%LOG_FILE%"
echo === [Step 2/3] Refresh company rich data === >> "%LOG_FILE%"
echo Start: %date% %time% >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"
"%PYTHON%" "site\fetch_company_rich.py" >> "%LOG_FILE%" 2>&1
set "RICH_RC=%errorlevel%"
if not "%RICH_RC%"=="0" (
    echo [WARN] rich refresh exit %RICH_RC%, continue to build step anyway >> "%LOG_FILE%"
)

REM --- Step 3/3: Build site (price / institutional / render 2700+ pages + limit-up from enriched-*.json) ---
echo. >> "%LOG_FILE%"
echo === [Step 3/3] Build site === >> "%LOG_FILE%"
echo Start: %date% %time% >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"
"%PYTHON%" "%BUILD_SCRIPT%" >> "%LOG_FILE%" 2>&1
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
REM  Run with DEPLOY=0 to disable
REM ===========================================================
if not defined DEPLOY set "DEPLOY=1"

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

REM --- Clear stale .git/index.lock (>5 min old) before any git op ---
REM Otherwise add/commit will fail silently and changes pile up locally.
if exist ".git\index.lock" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$lock = Get-Item -ErrorAction SilentlyContinue '.git\index.lock'; if ($lock -and $lock.LastWriteTime -lt (Get-Date).AddMinutes(-5)) { Write-Host '[INFO] Removing stale .git/index.lock (last modified:' $lock.LastWriteTime ')'; Remove-Item -Force '.git\index.lock'; exit 0 } elseif ($lock) { Write-Host '[WARN] .git/index.lock is fresh (<5 min), another git process may be running, skip deploy this round'; exit 1 } else { exit 0 }"
    if errorlevel 1 (
        echo [SKIP] Fresh git lock detected, will retry next scheduled run
        goto :END
    )
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

REM --- Pull remote first to avoid non-fast-forward rejection ---
REM     Conflict on dist/ artifacts prefers remote (-X theirs);
REM     our latest rebuild will override on next push anyway.
git fetch origin --quiet
git pull --rebase -X theirs origin main --quiet
if errorlevel 1 (
    echo [WARN] git pull --rebase failed, aborting and skipping push this round
    git rebase --abort >nul 2>&1
    goto :END
)

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
