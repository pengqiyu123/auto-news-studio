$ErrorActionPreference = "Stop"

param(
    [Parameter(Mandatory = $true)]
    [string]$Version
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path

Write-Host "[INFO] Building frontend..."
Push-Location (Join-Path $appRoot "frontend")
try {
    npm run build
} finally {
    Pop-Location
}

Write-Host "[INFO] Compiling backend..."
Push-Location $appRoot
try {
    .\.venv\Scripts\python.exe -m compileall backend/app
} finally {
    Pop-Location
}

$tag = "v$Version"
Write-Host "[INFO] Creating git tag $tag"
git tag $tag
git push origin master
git push origin $tag

Write-Host "[OK] Code and tag pushed."
Write-Host "[NEXT] Go to GitHub Releases and publish release $tag using docs/release/RELEASE_NOTES_$Version.md"
