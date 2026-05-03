$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$releaseRoot = Join-Path $appRoot "runtime\release"
$stageDir = Join-Path $releaseRoot "auto-news-studio-windows"
$zipPath = Join-Path $releaseRoot "auto-news-studio-windows.zip"

function Reset-Path([string]$path) {
    if (Test-Path $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}

function Ensure-Dir([string]$path) {
    New-Item -ItemType Directory -Path $path -Force | Out-Null
}

function Copy-FileSafe([string]$source, [string]$target) {
    Ensure-Dir (Split-Path -Parent $target)
    Copy-Item -LiteralPath $source -Destination $target -Force
}

function Copy-DirFiltered([string]$source, [string]$target, [string[]]$excludeDirs, [string[]]$excludeFiles) {
    Ensure-Dir $target
    Get-ChildItem -LiteralPath $source -Force | ForEach-Object {
        $name = $_.Name
        $dest = Join-Path $target $name
        if ($_.PSIsContainer) {
            if ($excludeDirs -contains $name) {
                return
            }
            Copy-DirFiltered $_.FullName $dest $excludeDirs $excludeFiles
        } else {
            foreach ($pattern in $excludeFiles) {
                if ($name -like $pattern) {
                    return
                }
            }
            Copy-FileSafe $_.FullName $dest
        }
    }
}

Reset-Path $stageDir
Reset-Path $zipPath
Ensure-Dir $stageDir

$backendTarget = Join-Path $stageDir "backend"
$frontendTarget = Join-Path $stageDir "frontend"
$scriptsTarget = Join-Path $stageDir "scripts"

Copy-DirFiltered (Join-Path $appRoot "backend\app") (Join-Path $backendTarget "app") @("__pycache__", ".ruff_cache", "data") @("*.pyc", "*.pyo", "*.log", "*.pid", ".env")
Copy-FileSafe (Join-Path $appRoot "backend\requirements.txt") (Join-Path $backendTarget "requirements.txt")

if (Test-Path (Join-Path $appRoot ".venv\Scripts\python.exe")) {
    Write-Host "[INFO] Bundling .venv into release (offline-ready)..."
    Copy-DirFiltered (Join-Path $appRoot ".venv") (Join-Path $stageDir ".venv") @("__pycache__", ".ruff_cache") @("*.pyc", "*.pyo", "*.log")
} else {
    Write-Host "[WARN] No .venv found in dev tree — release will require online install."
}

Copy-DirFiltered (Join-Path $appRoot "frontend\dist") (Join-Path $frontendTarget "dist") @() @()

Copy-FileSafe (Join-Path $appRoot "scripts\start_backend.ps1") (Join-Path $scriptsTarget "start_backend.ps1")
Copy-FileSafe (Join-Path $appRoot "scripts\stop_backend.ps1") (Join-Path $scriptsTarget "stop_backend.ps1")
Copy-FileSafe (Join-Path $appRoot "scripts\doctor.ps1") (Join-Path $scriptsTarget "doctor.ps1")

Copy-FileSafe (Join-Path $appRoot "start.bat") (Join-Path $stageDir "start.bat")
Copy-FileSafe (Join-Path $appRoot "stop.bat") (Join-Path $stageDir "stop.bat")
Copy-FileSafe (Join-Path $appRoot "install.bat") (Join-Path $stageDir "install.bat")
Copy-FileSafe (Join-Path $appRoot "doctor.bat") (Join-Path $stageDir "doctor.bat")
Copy-FileSafe (Join-Path $appRoot ".env.example") (Join-Path $stageDir ".env.example")
Copy-FileSafe (Join-Path $appRoot "version.json") (Join-Path $stageDir "version.json")
Copy-FileSafe (Join-Path $appRoot "README.md") (Join-Path $stageDir "README.md")
Copy-FileSafe (Join-Path $appRoot "LICENSE") (Join-Path $stageDir "LICENSE")
Copy-FileSafe (Join-Path $appRoot "docs\DISTRIBUTION.md") (Join-Path $stageDir "DISTRIBUTION.md")

Ensure-Dir (Join-Path $stageDir "config")
Ensure-Dir (Join-Path $stageDir "data")
Ensure-Dir (Join-Path $stageDir "logs")
Ensure-Dir (Join-Path $stageDir "runtime")

Compress-Archive -Path (Join-Path $stageDir "*") -DestinationPath $zipPath -Force
Write-Host "[OK] Release folder created: $stageDir"
Write-Host "[OK] Release zip created: $zipPath"
