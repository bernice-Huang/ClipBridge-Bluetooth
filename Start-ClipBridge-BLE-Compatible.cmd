@echo off
setlocal
chcp 65001 >nul
title ClipBridge Bluetooth 0.3.1-beta Compatibility Mode
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Python environment missing. Run Setup.ps1 first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -X utf8 "windows\sender.py" --pipeline 1
echo.
pause
