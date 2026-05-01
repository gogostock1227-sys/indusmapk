@echo off
chcp 65001 > nul
setlocal

set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%\setup_daily_schedule.ps1"
set "RC=%errorlevel%"

if /i "%1" neq "quiet" (
    echo.
    echo Press any key to close...
    pause > nul
)

exit /b %RC%
