@echo off
title Stop Naukri Bot
color 0C

cd /d "%~dp0"

echo ===================================================
echo        STOPPING NAUKRI BOT SERVERS
echo ===================================================
echo.

echo Terminating Backend and Frontend processes...

:: 1. Terminate windows by Title
taskkill /fi "WINDOWTITLE eq Naukri Bot Backend*" /f /t >nul 2>&1
taskkill /fi "WINDOWTITLE eq Naukri Bot Frontend*" /f /t >nul 2>&1

:: 2. Terminate any orphan processes holding port 8000 or 5173
set "PYTHON_EXE=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if exist "%~dp0venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
"%PYTHON_EXE%" "%~dp0scripts\kill_servers.py" >nul 2>&1

echo.
echo [OK] All servers stopped successfully.
echo.
timeout /t 2 /nobreak >nul
