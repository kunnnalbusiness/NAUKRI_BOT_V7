@echo off
title Naukri Bot Backend
color 0B
cd /d "%~dp0.."

echo ===================================================
echo             NAUKRI BOT - FASTAPI BACKEND
echo ===================================================
echo.
echo Starting Uvicorn on http://127.0.0.1:8000 ...
echo.

set "PY=python"
if exist "%~dp0..\.venv\Scripts\python.exe" set "PY=%~dp0..\.venv\Scripts\python.exe"
if exist "%~dp0..\venv\Scripts\python.exe" set "PY=%~dp0..\venv\Scripts\python.exe"

"%PY%" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Backend stopped unexpectedly with error code %errorlevel%!
    echo.
    pause
)
