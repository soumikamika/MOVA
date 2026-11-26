@echo off
setlocal
cd /d "%~dp0"
echo ========================================
echo       MOVA FRONTEND
echo ========================================
echo.
where py >nul 2>nul
if %errorlevel%==0 (
    echo MOVA website: http://127.0.0.1:5500
    echo Keep this window open while using MOVA.
    echo.
    py -m http.server 5500 --bind 127.0.0.1
    exit /b %errorlevel%
)
where python >nul 2>nul
if %errorlevel%==0 (
    echo MOVA website: http://127.0.0.1:5500
    echo Keep this window open while using MOVA.
    echo.
    python -m http.server 5500 --bind 127.0.0.1
    exit /b %errorlevel%
)
echo ERROR: Python was not found.
pause
exit /b 1
