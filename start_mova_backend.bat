@echo off
setlocal
cd /d "%~dp0backend\mova_travel_engine"

echo ========================================
echo       MOVA TRAVEL ENGINE
 echo ========================================
echo.

set "PYTHON_CMD="
where py >nul 2>nul
if %errorlevel%==0 (
    py -c "import sys; print(sys.version)" >nul 2>nul
    if %errorlevel%==0 set "PYTHON_CMD=py"
)
if not defined PYTHON_CMD (
    where python >nul 2>nul
    if %errorlevel%==0 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
    echo ERROR: Python was not found.
    echo Install Python 3.11+ and make sure it is available from the terminal.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating MOVA backend virtual environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo ERROR: Could not create the virtual environment.
        pause
        exit /b 1
    )
)

echo Installing/checking backend dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: pip setup failed.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Dependency installation failed.
    pause
    exit /b 1
)

echo.
echo ========================================
echo MOVA API: http://127.0.0.1:8000
echo Health:  http://127.0.0.1:8000/api/health
echo Keep this window open while using MOVA.
echo ========================================
echo.
".venv\Scripts\python.exe" -m uvicorn app.api.app:app --host 127.0.0.1 --port 8000

echo.
echo MOVA backend stopped.
pause
