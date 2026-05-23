$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path

$dataDir = Join-Path $appRoot "data"
$dataStateDir = Join-Path $dataDir "state"
$runtimeDir = Join-Path $appRoot "runtime"
$runtimeCacheDir = Join-Path $runtimeDir "cache"
$runtimeLogDir = Join-Path $runtimeDir "logs"
$runtimeTempDir = Join-Path $runtimeDir "temp"
$distDir = Join-Path $appRoot "dist"
$distWindowsDir = Join-Path $distDir "windows"
$archiveDir = Join-Path $runtimeDir "migration-archive"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$archiveRunDir = Join-Path $archiveDir $stamp

$newStateFile = Join-Path $dataStateDir "state.json"
$legacyStateFile = Join-Path $dataDir "state.json"
$legacyBackendStateFile = Join-Path $appRoot "backend\data\state.json"
$legacyBackendStateBakFile = Join-Path $appRoot "backend\data\state.json.bak"

function Ensure-Dir([string]$path) {
    New-Item -ItemType Directory -Path $path -Force | Out-Null
}

function Move-IfExists([string]$source, [string]$target) {
    if (-not (Test-Path $source)) {
        return
    }
    Ensure-Dir (Split-Path -Parent $target)
    if (Test-Path $target) {
        Write-Host "[INFO] Skip move because target exists: $target"
        return
    }
    Move-Item -LiteralPath $source -Destination $target
    Write-Host "[OK] Moved: $source -> $target"
}

function Archive-IfExists([string]$source, [string]$archiveRoot) {
    if (-not (Test-Path $source)) {
        return
    }
    Ensure-Dir $archiveRoot
    $target = Join-Path $archiveRoot (Split-Path $source -Leaf)
    if (Test-Path $target) {
        $target = Join-Path $archiveRoot ((Split-Path $source -Leaf) + ".dup")
    }
    Move-Item -LiteralPath $source -Destination $target
    Write-Host "[OK] Archived: $source -> $target"
}

function Get-JsonSummary([string]$path) {
    if (-not (Test-Path $path)) {
        return $null
    }
    $json = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    $runtime = $json.runtime
    $meta = $json.app_meta
    [PSCustomObject]@{
        Path = $path
        Size = (Get-Item $path).Length
        LastWriteTime = (Get-Item $path).LastWriteTime
        RawItems = @($json.raw_items).Count
        Briefs = @($json.briefs).Count
        Logs = @($json.logs).Count
        LastCollectAt = if ($runtime) { [string]$runtime.last_collect_at } else { "" }
        LastUpdateCheck = if ($meta -and $meta.last_update_check) { [string]$meta.last_update_check.checked_at } else { "" }
        Hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    }
}

Ensure-Dir $dataStateDir
Ensure-Dir $runtimeCacheDir
Ensure-Dir $runtimeLogDir
Ensure-Dir $runtimeTempDir
Ensure-Dir $distWindowsDir

$stateCandidates = @($newStateFile, $legacyStateFile, $legacyBackendStateFile) | Where-Object { Test-Path $_ }
$stateSummaries = @()
foreach ($path in $stateCandidates) {
    $stateSummaries += Get-JsonSummary $path
}

Write-Host "[INFO] State file summary:"
$stateSummaries | Format-Table Path,Size,LastWriteTime,RawItems,Briefs,Logs,LastCollectAt,LastUpdateCheck -AutoSize

$distinctHashes = @($stateSummaries | Select-Object -ExpandProperty Hash -Unique)
$hasStateConflict = ($distinctHashes.Count -gt 1)

if ($hasStateConflict) {
    Write-Host "[WARN] Multiple state files differ. Automatic cleanup of legacy state files is skipped."
    Ensure-Dir $archiveRunDir
    $stateSummaries | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $archiveRunDir "state-summary.json") -Encoding UTF8
} else {
    if (Test-Path $legacyStateFile) {
        Archive-IfExists $legacyStateFile (Join-Path $archiveRunDir "legacy-data-state")
    }
    if (Test-Path $legacyBackendStateFile) {
        Archive-IfExists $legacyBackendStateFile (Join-Path $archiveRunDir "legacy-backend-state")
    }
}

if (Test-Path $legacyBackendStateBakFile) {
    Archive-IfExists $legacyBackendStateBakFile (Join-Path $archiveRunDir "legacy-backend-state")
}

Move-IfExists (Join-Path $runtimeDir "agent_html_cache") (Join-Path $runtimeCacheDir "agent_html")
Move-IfExists (Join-Path $runtimeDir "backend.err.log") (Join-Path $runtimeLogDir "backend.err.log")
Move-IfExists (Join-Path $runtimeDir "backend.out.log") (Join-Path $runtimeLogDir "backend.out.log")
Move-IfExists (Join-Path $runtimeDir "backend.pid") (Join-Path $runtimeLogDir "backend.pid")
Move-IfExists (Join-Path $runtimeDir "probe.err.log") (Join-Path $runtimeLogDir "probe.err.log")
Move-IfExists (Join-Path $runtimeDir "probe.out.log") (Join-Path $runtimeLogDir "probe.out.log")
if (Test-Path (Join-Path $runtimeDir "release")) {
    Ensure-Dir $distWindowsDir
    Get-ChildItem -LiteralPath (Join-Path $runtimeDir "release") -Force | ForEach-Object {
        Move-IfExists $_.FullName (Join-Path $distWindowsDir $_.Name)
    }
}
Move-IfExists (Join-Path $appRoot "backend\data\artifacts") (Join-Path $runtimeTempDir "publish_artifacts")

if (Test-Path (Join-Path $appRoot "logs")) {
    Ensure-Dir (Join-Path $archiveRunDir "legacy-logs")
    Get-ChildItem -LiteralPath (Join-Path $appRoot "logs") -File -ErrorAction SilentlyContinue | ForEach-Object {
        Move-IfExists $_.FullName (Join-Path $runtimeLogDir $_.Name)
    }
}

Write-Host "[OK] Runtime layout migration finished."
if ($hasStateConflict) {
    Write-Host "[WARN] Legacy state files were not deleted because their contents differ."
    Write-Host "[WARN] Review the summary in: $archiveRunDir"
}
