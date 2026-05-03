$ErrorActionPreference = "Stop"

function Get-ListenerPid {
    try {
        $listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction Stop |
            Select-Object -First 1
        if ($listener) {
            return [int]$listener.OwningProcess
        }
    } catch {
    }
    return $null
}

function Get-ProjectBackendProcesses {
    @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -eq "python.exe" -and ([string]$_.CommandLine) -like "*backend.app.main:app*"
    })
}

function Stop-ProjectBackendProcesses {
    $projectBackends = @(Get-ProjectBackendProcesses)
    foreach ($proc in $projectBackends) {
        Write-Host "[WARN] Stopping project backend PID=$($proc.ProcessId)"
        Stop-Process -Id ([int]$proc.ProcessId) -Force -ErrorAction SilentlyContinue
    }
    if ($projectBackends.Count -gt 0) {
        Start-Sleep -Seconds 2
    }
}

function Get-ProcessInfo([int]$ProcessId) {
    Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
}

function Is-ProjectBackend($ProcessInfo) {
    if (-not $ProcessInfo) {
        return $false
    }
    return ([string]$ProcessInfo.CommandLine) -like "*backend.app.main:app*"
}

function Is-BackedByVenv($ProcessInfo, [string]$VenvPythonPath) {
    if (-not $ProcessInfo) {
        return $false
    }
    $exePath = [string]$ProcessInfo.ExecutablePath
    if ($exePath -and $exePath -ieq $VenvPythonPath) {
        return $true
    }
    $parentPidValue = $ProcessInfo.ParentProcessId
    if ($null -eq $parentPidValue) {
        $parentPidValue = 0
    }
    $parentPid = [int]$parentPidValue
    if ($parentPid -le 0) {
        return $false
    }
    $parentProc = Get-ProcessInfo -ProcessId $parentPid
    if (-not $parentProc) {
        return $false
    }
    return ([string]$parentProc.ExecutablePath) -ieq $VenvPythonPath
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$venvPython = Join-Path $appRoot ".venv\Scripts\python.exe"
$runtimeDir = Join-Path $appRoot "runtime"
$pidFile = Join-Path $runtimeDir "backend.pid"
$outLog = Join-Path $runtimeDir "backend.out.log"
$errLog = Join-Path $runtimeDir "backend.err.log"
$frontendDist = Join-Path $appRoot "frontend\dist\index.html"
$appUrl = "http://127.0.0.1:8000"

if (-not (Test-Path $runtimeDir)) {
    New-Item -ItemType Directory -Path $runtimeDir | Out-Null
}

if (-not (Test-Path $venvPython)) {
    Write-Host "[ERROR] Virtual environment not found: $venvPython"
    Write-Host "Please check whether .venv exists in this project."
    exit 1
}

if (-not (Test-Path $frontendDist)) {
    Write-Host "[INFO] Frontend dist not found, building frontend..."
    Push-Location (Join-Path $appRoot "frontend")
    try {
        & npm run build
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] Frontend build failed."
            exit 1
        }
    } finally {
        Pop-Location
    }
}

$projectBackends = @(Get-ProjectBackendProcesses)
if ($projectBackends.Count -gt 0) {
    $staleBackends = @()
    $healthyVenvBackend = $null
    foreach ($proc in $projectBackends) {
        if (Is-BackedByVenv $proc $venvPython) {
            if (-not $healthyVenvBackend) {
                $healthyVenvBackend = $proc
            } else {
                $staleBackends += $proc
            }
        } else {
            $staleBackends += $proc
        }
    }

    foreach ($proc in $staleBackends) {
        Write-Host "[WARN] Stopping stale project backend PID=$($proc.ProcessId)"
        Stop-Process -Id ([int]$proc.ProcessId) -Force -ErrorAction SilentlyContinue
    }
    if ($staleBackends.Count -gt 0) {
        Start-Sleep -Seconds 2
    }

    if ($healthyVenvBackend) {
        $listenerPid = Get-ListenerPid
        if ($listenerPid -and $listenerPid -eq [int]$healthyVenvBackend.ProcessId) {
            Set-Content -Path $pidFile -Value $listenerPid
            Write-Host "[INFO] Auto News Studio is already running. PID=$listenerPid"
            Write-Host "URL: $appUrl"
            Start-Process $appUrl | Out-Null
            exit 0
        }
    }
}

$listenerPid = Get-ListenerPid
if ($listenerPid) {
    $listenerProc = Get-ProcessInfo -ProcessId $listenerPid
    if (Is-ProjectBackend $listenerProc) {
        if (Is-BackedByVenv $listenerProc $venvPython) {
            Set-Content -Path $pidFile -Value $listenerPid
            Write-Host "[INFO] Auto News Studio is already running. PID=$listenerPid"
            Write-Host "URL: $appUrl"
            Start-Process $appUrl | Out-Null
            exit 0
        }

        Write-Host "[WARN] Detected stale Auto News Studio backend on port 8000. PID=$listenerPid"
        Write-Host "[INFO] Stopping stale process and restarting with project .venv..."
        Stop-Process -Id $listenerPid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    } else {
        Write-Host "[ERROR] Port 8000 is occupied by another process. PID=$listenerPid"
        Write-Host "[ERROR] Please free port 8000 first, then start Auto News Studio again."
        exit 1
    }
}

if (Test-Path $pidFile) {
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

$listenerPid = Get-ListenerPid
if ($listenerPid) {
    Write-Host "[WARN] Port 8000 is already in use by PID $listenerPid"
    Write-Host "Run stop.bat first, or close the process manually."
    exit 1
}

Write-Host "[INFO] Starting Auto News Studio..."

$process = Start-Process -FilePath $venvPython `
    -ArgumentList @("-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $appRoot `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -PassThru `
    -WindowStyle Hidden

$startedPid = [int]$process.Id
$ready = $false

for ($i = 0; $i -lt 45; $i++) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8000/api/health" -TimeoutSec 2
        $currentListenerPid = Get-ListenerPid
        $currentListenerProc = if ($currentListenerPid) { Get-ProcessInfo -ProcessId $currentListenerPid } else { $null }
        if (
            ($response.StatusCode -eq 200) -and
            [bool]$currentListenerPid -and
            (Is-ProjectBackend $currentListenerProc) -and
            (Is-BackedByVenv $currentListenerProc $venvPython)
        ) {
            $ready = $true
            break
        }
    } catch {
    }
    Start-Sleep -Seconds 1
}

if (-not $ready) {
    Stop-ProjectBackendProcesses
    if (Test-Path $pidFile) {
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    }
    Write-Host "[ERROR] Failed to detect backend listener on port 8000."
    if (Test-Path $errLog) {
        Write-Host "[ERROR] Backend stderr tail:"
        Get-Content -Path $errLog -Tail 20 -ErrorAction SilentlyContinue
    }
    exit 1
}

$listenerPid = Get-ListenerPid
if ($listenerPid) {
    Set-Content -Path $pidFile -Value $listenerPid
} elseif (Test-Path $pidFile) {
    $listenerPid = (Get-Content -Path $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
}

Write-Host ""
Write-Host "========================================"
Write-Host "  Auto News Studio started successfully"
Write-Host "========================================"
Write-Host "  PID:  $listenerPid"
Write-Host "  URL:  $appUrl"
Write-Host "  Logs: $runtimeDir\"
Write-Host "========================================"
Write-Host ""

Start-Process $appUrl | Out-Null
exit 0
