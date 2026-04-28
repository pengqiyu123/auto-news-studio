@echo off
setlocal EnableDelayedExpansion

cd /d "%~dp0"

set "APP_ROOT=%~dp0"
set "VENV_PYTHON=%APP_ROOT%.venv\Scripts\python.exe"
set "RUNTIME_DIR=%APP_ROOT%runtime"
set "PID_FILE=%RUNTIME_DIR%\backend.pid"
set "OUT_LOG=%RUNTIME_DIR%\backend.out.log"
set "ERR_LOG=%RUNTIME_DIR%\backend.err.log"
set "FRONTEND_DIST=%APP_ROOT%frontend\dist\index.html"

if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"

if not exist "%VENV_PYTHON%" (
  echo [ERROR] Virtual environment not found: %VENV_PYTHON%
  echo Please check whether .venv exists in this project.
  pause
  exit /b 1
)

if not exist "%FRONTEND_DIST%" (
  echo [INFO] Frontend dist not found, building frontend...
  pushd "%APP_ROOT%frontend"
  call npm run build
  if errorlevel 1 (
    popd
    echo [ERROR] Frontend build failed.
    pause
    exit /b 1
  )
  popd
)

if exist "%PID_FILE%" (
  set /p EXISTING_PID=<"%PID_FILE%"
  echo(!EXISTING_PID!| findstr /R "^[0-9][0-9]*$" >nul 2>nul
  if not errorlevel 1 if not "!EXISTING_PID!"=="" (
    tasklist /FI "PID eq !EXISTING_PID!" | find "!EXISTING_PID!" >nul 2>nul
    if not errorlevel 1 (
      for /f %%P in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "$pid = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue ^| Select-Object -First 1 -ExpandProperty OwningProcess; if ($pid) { Write-Output $pid }"') do (
        set "ACTIVE_LISTENER_PID=%%P"
      )
      if defined ACTIVE_LISTENER_PID (
        echo [INFO] Auto News Studio is already running. PID=!EXISTING_PID!
        echo URL: http://127.0.0.1:8000
        pause
        exit /b 0
      ) else (
        echo [INFO] Found stale backend parent process, cleaning up PID !EXISTING_PID!.
        taskkill /PID !EXISTING_PID! /T /F >nul 2>nul
        del /q "%PID_FILE%" >nul 2>nul
      )
    ) else (
      echo [INFO] Stale PID file found, cleaning up.
      del /q "%PID_FILE%" >nul 2>nul
    )
  )
)

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do (
  echo [WARN] Port 8000 is already in use by PID %%P
  echo Run stop.bat first, or close the process manually.
  pause
  exit /b 1
)

echo [INFO] Starting Auto News Studio...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$wd = '%APP_ROOT%';" ^
  "$py = '%VENV_PYTHON%';" ^
  "$out = '%OUT_LOG%';" ^
  "$err = '%ERR_LOG%';" ^
  "$p = Start-Process -FilePath $py -ArgumentList '-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $wd -RedirectStandardOutput $out -RedirectStandardError $err -PassThru -WindowStyle Hidden;" ^
  "Set-Content -Path '%PID_FILE%' -Value $p.Id"

timeout /t 3 /nobreak >nul

set "STARTED_PID="
for /f %%P in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "$pid = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue ^| Select-Object -First 1 -ExpandProperty OwningProcess; if ($pid) { Write-Output $pid }"') do (
  set "STARTED_PID=%%P"
)

if not defined STARTED_PID (
  echo [ERROR] Failed to detect backend listener on port 8000.
  pause
  exit /b 1
)

echo.
echo ========================================
echo   Auto News Studio started successfully
echo ========================================
set "PARENT_PID="
if exist "%PID_FILE%" set /p PARENT_PID=<"%PID_FILE%"
echo   PID:  !STARTED_PID!
if defined PARENT_PID if not "!PARENT_PID!"=="!STARTED_PID!" echo   Tree: !PARENT_PID! -> !STARTED_PID!
echo   URL:  http://127.0.0.1:8000
echo   Logs: %RUNTIME_DIR%\
echo ========================================
echo.

start http://127.0.0.1:8000

exit /b 0
