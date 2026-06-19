@echo off
title AgriSearch – Startup
color 0A

echo.
echo  ╔══════════════════════════════════════╗
echo  ║       AgriSearch Farm System         ║
echo  ║         Startup Launcher             ║
echo  ╚══════════════════════════════════════╝
echo.

:: ── 1. Check Python ──────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python is not installed or not in PATH.
    echo          Download it from https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  [OK] Found %%v

:: ── 2. Create virtual environment if missing ─────────────────
if not exist ".venv\Scripts\activate.bat" (
    echo.
    echo  [SETUP] Creating virtual environment (.venv)...
    python -m venv .venv
    if errorlevel 1 (
        echo  [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  [OK] Virtual environment created.
) else (
    echo  [OK] Virtual environment already exists.
)

:: ── 3. Activate virtual environment ──────────────────────────
echo.
echo  [INFO] Activating virtual environment...
call .venv\Scripts\activate.bat

:: ── 4. Install / update dependencies ─────────────────────────
echo.
echo  [INFO] Installing dependencies from requirements.txt...
pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo  [ERROR] Failed to install requirements.
    pause
    exit /b 1
)
echo  [OK] Dependencies ready.

:: ── 5. Check .env file ───────────────────────────────────────
echo.
if not exist ".env" (
    echo  [WARN] No .env file found!
    echo         Please create one with DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, SECRET_KEY, etc.
    echo         See README.md for reference.
    pause
    exit /b 1
) else (
    echo  [OK] .env file found.
)

:: ── 6. Launch application ─────────────────────────────────────
echo.
echo  [INFO] Starting AgriSearch...
echo  [INFO] The database and all tables will be created automatically on first run.
echo  [INFO] Open your browser at: http://localhost:5000
echo  ──────────────────────────────────────────
echo.
python run.py

:: ── Keep window open on crash ────────────────────────────────
echo.
echo  [INFO] Server stopped.
pause
