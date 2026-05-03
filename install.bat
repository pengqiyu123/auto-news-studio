@echo off
setlocal

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python 3.11+ not found in PATH.
  exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo [ERROR] Python 3.11+ is required.
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [INFO] Creating virtual environment...
  python -m venv .venv
  echo [INFO] Installing backend dependencies...
  ".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
  if errorlevel 1 exit /b 1
  echo [INFO] Installing Playwright browser...
  ".venv\Scripts\python.exe" -m playwright install chromium
  if errorlevel 1 exit /b 1
) else (
  echo [INFO] Virtual environment already exists, skipping install.
)

if not exist "config" mkdir config
if not exist "data" mkdir data
if not exist "logs" mkdir logs
if not exist "runtime" mkdir runtime

if not exist "frontend\dist\index.html" (
  echo [ERROR] Missing frontend dist. This package is incomplete.
  exit /b 1
)

echo [OK] Install finished. Run start.bat to launch Auto News Studio.
exit /b 0
