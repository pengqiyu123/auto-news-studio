@echo off
setlocal EnableDelayedExpansion

cd /d "%~dp0"

set "APP_ROOT=%~dp0"
set "RUNTIME_DIR=%APP_ROOT%runtime"
set "PID_FILE=%RUNTIME_DIR%\backend.pid"
set "STOPPED=0"

echo [INFO] Stopping Auto News Studio...

if exist "%PID_FILE%" (
  set /p TARGET_PID=<"%PID_FILE%"
  echo(!TARGET_PID!| findstr /R "^[0-9][0-9]*$" >nul 2>nul
  if not errorlevel 1 if not "!TARGET_PID!"=="" (
    tasklist /FI "PID eq !TARGET_PID!" | find "!TARGET_PID!" >nul 2>nul
    if not errorlevel 1 (
      echo [INFO] Stopping PID !TARGET_PID!...
      taskkill /PID !TARGET_PID! /T /F >nul 2>nul
      if not errorlevel 1 (
        echo [INFO] Stopped PID !TARGET_PID!
        set "STOPPED=1"
        set "KILLED_!TARGET_PID!=1"
      )
    )
  ) else (
    if not "!TARGET_PID!"=="" (
      echo [WARN] Ignoring invalid PID file content: !TARGET_PID!
    )
  )
  del /q "%PID_FILE%" >nul 2>nul
)

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do (
  if not "!KILLED_%%P!"=="1" (
    echo [INFO] Stopping listener on port 8000. PID=%%P
    taskkill /PID %%P /T /F >nul 2>nul
    if not errorlevel 1 (
      echo [INFO] Stopped PID %%P
      set "STOPPED=1"
      set "KILLED_%%P!=1"
    )
  )
)

set "PORT_STILL_BUSY=0"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do (
  set "PORT_STILL_BUSY=1"
  echo [WARN] Port 8000 is still in use by PID %%P
)

if "!STOPPED!"=="1" (
  if "!PORT_STILL_BUSY!"=="0" (
    echo [OK] Auto News Studio has been stopped.
  ) else (
    echo [WARN] Port 8000 is still in use. You may need to close it manually.
  )
) else (
  if "!PORT_STILL_BUSY!"=="1" (
    echo [WARN] Port 8000 is occupied by an unknown process.
  ) else (
    echo [INFO] Auto News Studio is not running.
  )
)

exit /b 0
