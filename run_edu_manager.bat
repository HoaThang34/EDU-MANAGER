@echo off
echo ==========================================
echo       EDU-MANAGER LAUNCHER
echo ==========================================

REM 1. Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python from https://www.python.org/downloads/
    pause
    exit /b
)

REM 2. Check/Create Virtual Environment
if not exist ".venv" (
    echo [INFO] Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b
    )
)

REM 3. Activate Virtual Environment
call .venv\Scripts\activate
if %errorlevel% neq 0 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b
)

REM 4. Install Dependencies
if exist "requirements.txt" (
    echo [INFO] Installing/Updating dependencies...
    pip install -r requirements.txt >nul
    if %errorlevel% neq 0 (
        echo [WARNING] Some dependencies might have failed to install.
    ) else (
        echo [SUCCESS] Dependencies are ready.
    )
) else (
    echo [WARNING] requirements.txt not found. Skipping dependency installation.
)

REM 5. Run the Application
echo.
echo [INFO] Starting the application...
echo [INFO] Please open your browser to http://127.0.0.1:5000 if it doesn't open automatically.
echo.
python app.py

pause
