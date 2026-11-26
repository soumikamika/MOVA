@echo off
setlocal
cd /d "%~dp0"
start "MOVA Backend" cmd /k call "%~dp0start_mova_backend.bat"
timeout /t 2 /nobreak >nul
start "MOVA Frontend" cmd /k call "%~dp0start_mova_frontend.bat"
timeout /t 2 /nobreak >nul
start "MOVA Browser" http://127.0.0.1:5500/
echo MOVA is starting.
echo Backend:  http://127.0.0.1:8000
 echo Frontend: http://127.0.0.1:5500
