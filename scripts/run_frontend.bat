@echo off
title Naukri Bot Frontend
color 0E
cd /d "%~dp0..\frontend"

echo ===================================================
echo             NAUKRI BOT - VITE FRONTEND
echo ===================================================
echo.
echo Starting Vite on http://localhost:5173 ...
echo.

call npm run dev

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Frontend stopped unexpectedly with error code %errorlevel%!
    echo.
    pause
)
