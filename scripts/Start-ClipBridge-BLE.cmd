@echo off
setlocal
chcp 65001 >nul
title ClipBridge Bluetooth - console diagnostics
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo Python environment missing. Run scripts\Setup.ps1 first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -X utf8 "windows\console.py"
echo.
pause
