$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\backend\mova_travel_engine"

Write-Host "========================================"
Write-Host "       MOVA TRAVEL ENGINE"
Write-Host "========================================"
Write-Host ""

$pythonCmd = $null
if (Get-Command py -ErrorAction SilentlyContinue) { $pythonCmd = "py" }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $pythonCmd = "python" }

if (-not $pythonCmd) {
    Write-Host "ERROR: Python was not found. Install Python 3.11+ and add it to PATH."
    Read-Host "Press Enter to close"
    exit 1
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating MOVA backend virtual environment..."
    & $pythonCmd -m venv .venv
}

Write-Host "Installing/checking backend dependencies..."
& ".venv\Scripts\python.exe" -m pip install --upgrade pip
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Host ""
Write-Host "========================================"
Write-Host "MOVA API: http://127.0.0.1:8000"
Write-Host "Health:  http://127.0.0.1:8000/api/health"
Write-Host "Keep this window open while using MOVA."
Write-Host "========================================"
Write-Host ""
& ".venv\Scripts\python.exe" -m uvicorn app.api.app:app --host 127.0.0.1 --port 8000
