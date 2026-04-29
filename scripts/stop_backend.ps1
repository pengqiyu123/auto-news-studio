$ErrorActionPreference = "Stop"

function Get-ListenerPids {
    try {
        $listeners = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction Stop
        return @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    } catch {
        return @()
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

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$runtimeDir = Join-Path $appRoot "runtime"
$pidFile = Join-Path $runtimeDir "backend.pid"
$stopped = $false
$killed = [System.Collections.Generic.HashSet[int]]::new()

Write-Host "[INFO] Stopping Auto News Studio..."

foreach ($proc in @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    ([string]$_.CommandLine) -like "*backend.app.main:app*"
})) {
    $procId = [int]$proc.ProcessId
    if ($killed.Contains($procId)) {
        continue
    }
    Write-Host "[INFO] Stopping Auto News Studio backend PID $procId..."
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    $null = $killed.Add($procId)
    $stopped = $true
}

if (Test-Path $pidFile) {
    $pidText = (Get-Content -Path $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    if ($pidText -match '^\d+$') {
        $pidValue = [int]$pidText
        if (-not $killed.Contains($pidValue) -and (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)) {
            Write-Host "[INFO] Stopping PID $pidValue..."
            Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
            $null = $killed.Add($pidValue)
            $stopped = $true
        }
    } elseif ($pidText) {
        Write-Host "[WARN] Ignoring invalid PID file content: $pidText"
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

foreach ($listenerPid in Get-ListenerPids) {
    $pidValue = [int]$listenerPid
    if ($killed.Contains($pidValue)) {
        continue
    }
    $proc = Get-ProcessInfo -ProcessId $pidValue
    if (Is-ProjectBackend $proc) {
        Write-Host "[INFO] Stopping listener on port 8000. PID=$pidValue"
        Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
        $null = $killed.Add($pidValue)
        $stopped = $true
    } else {
        Write-Host "[WARN] Port 8000 is occupied by a non-project process. PID=$pidValue"
    }
}

$remainingListeners = Get-ListenerPids
if ($stopped) {
    if ($remainingListeners.Count -eq 0) {
        Write-Host "[OK] Auto News Studio has been stopped."
        exit 0
    }
    foreach ($listenerPid in $remainingListeners) {
        Write-Host "[WARN] Port 8000 is still in use by PID $listenerPid"
    }
    Write-Host "[WARN] Port 8000 is still in use. You may need to close it manually."
    exit 1
}

if ($remainingListeners.Count -gt 0) {
    foreach ($listenerPid in $remainingListeners) {
        Write-Host "[WARN] Port 8000 is occupied by an unknown process. PID=$listenerPid"
    }
    exit 1
}

Write-Host "[INFO] Auto News Studio is not running."
exit 0
