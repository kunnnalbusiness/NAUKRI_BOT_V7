@echo off
setlocal enabledelayedexpansion
title Naukri & LinkedIn Bot Launcher
color 0A

:: Navigate to project root directory
cd /d "%~dp0"

echo ===================================================
echo        NAUKRI ^& LINKEDIN AUTOMATION BOT
echo ===================================================
echo.

:: 1. Detect Python interpreter (venv or global)
set "PYTHON_EXE="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
    echo [OK] Using virtual environment: .venv
) else if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
    echo [OK] Using virtual environment: venv
) else (
    where.exe python >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=python"
    ) else (
        where.exe py >nul 2>&1
        if !errorlevel! equ 0 (
            set "PYTHON_EXE=py -3"
        )
    )
)

if not defined PYTHON_EXE (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10+ and add it to PATH.
    echo Download from: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:: Verify Python executable
"%PYTHON_EXE%" --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python interpreter failed to run: %PYTHON_EXE%
    pause
    exit /b 1
)

:: 2. Detect Node.js & npm
where.exe node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed or not in PATH!
    echo Please install Node.js from: https://nodejs.org/
    echo.
    pause
    exit /b 1
)

where.exe npm >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] npm is not installed or not in PATH!
    echo Please reinstall Node.js and ensure npm is added to PATH.
    echo.
    pause
    exit /b 1
)

echo [OK] Python and Node.js verified.

:: 3. Check and install backend dependencies if missing
"%PYTHON_EXE%" -c "import uvicorn, fastapi" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Backend dependencies missing. Installing requirements...
    "%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt"
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install backend dependencies.
        pause
        exit /b 1
    )
)

:: 4. Check and install frontend node_modules if missing
if not exist "%~dp0frontend\node_modules" (
    echo [INFO] Frontend node_modules missing. Installing npm packages...
    cd /d "%~dp0frontend"
    call npm install
    cd /d "%~dp0"
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install frontend dependencies.
        pause
        exit /b 1
    )
)

:: 5. Release any conflicting processes on port 8000 or 5173
"%PYTHON_EXE%" "%~dp0scripts\kill_servers.py" >nul 2>&1

:: 6. Start Backend server
echo [1/3] Starting FastAPI Backend on port 8000...
start "Naukri Bot Backend" cmd /k "%~dp0scripts\run_backend.bat"

:: 7. Start Frontend server
echo [2/3] Starting React Frontend on port 5173...
start "Naukri Bot Frontend" cmd /k "%~dp0scripts\run_frontend.bat"

:: 8. Wait for servers to spin up
echo [3/3] Waiting for servers to initialize...
set /a ATTEMPTS=0

:POLL_LOOP
timeout /t 1 /nobreak >nul
set /a ATTEMPTS+=1

"%PYTHON_EXE%" -c "import socket, sys; s = socket.socket(); sys.exit(s.connect_ex(('127.0.0.1', 8000)))" >nul 2>&1
set BACKEND_READY=%errorlevel%

"%PYTHON_EXE%" -c "import socket, sys; s = socket.socket(); sys.exit(s.connect_ex(('127.0.0.1', 5173)))" >nul 2>&1
set FRONTEND_READY=%errorlevel%

if %BACKEND_READY% equ 0 if %FRONTEND_READY% equ 0 goto READY

if %ATTEMPTS% lss 25 goto POLL_LOOP

:READY
echo.
echo ===================================================
echo   Automation servers are now running!
echo   - Backend:  http://127.0.0.1:8000
echo   - Frontend: http://localhost:5173
echo.
echo   Keep the server terminal windows open while using.
echo   To stop all servers, run stop.bat or close windows.
echo ===================================================
echo.

:: 9. Launch browser
echo Opening Dashboard in browser: http://localhost:5173
start http://localhost:5173

pause
