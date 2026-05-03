$ErrorActionPreference = "Continue"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path

Write-Host "[INFO] Auto News Studio doctor"

if (Get-Command python -ErrorAction SilentlyContinue) {
    Write-Host "[ OK ] Python found"
} else {
    Write-Host "[FAIL] Python not found in PATH"
}

$venvPython = Join-Path $appRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    Write-Host "[ OK ] Virtual environment exists"
} else {
    Write-Host "[FAIL] Virtual environment missing. Run install.bat first."
}

$frontendDist = Join-Path $appRoot "frontend\dist\index.html"
if (Test-Path $frontendDist) {
    Write-Host "[ OK ] Frontend dist exists"
} else {
    Write-Host "[FAIL] Frontend dist missing"
}

try {
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/admin/system/doctor" -TimeoutSec 3
    $item = $response.item
    Write-Host "[INFO] Backend doctor summary: $($item.summary)"
    foreach ($row in $item.items) {
        $status = if ($row.ok) { "OK" } else { "FAIL" }
        Write-Host "[$status] $($row.label): $($row.detail)"
        if ($row.next_action) {
            Write-Host "       Next: $($row.next_action)"
        }
    }
} catch {
    Write-Host "[WARN] Backend doctor unavailable. Start the app first."
}
