$ErrorActionPreference = "Stop"

function Get-PsqlPath {
    param(
        [string]$AppRoot
    )

    $localPsql = Join-Path $AppRoot "runtime\postgresql\16\bin\psql.exe"
    if (Test-Path $localPsql) {
        return $localPsql
    }

    $command = Get-Command psql -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "psql not found. Install PostgreSQL first."
}

function Parse-DatabaseUrl {
    param(
        [string]$DatabaseUrl
    )

    $pattern = '^postgresql\+psycopg://(?<user>[^:]+):(?<password>[^@]+)@(?<host>[^:\/]+):(?<port>\d+)\/(?<database>[^?\s]+)$'
    $match = [regex]::Match($DatabaseUrl, $pattern)
    if (-not $match.Success) {
        throw "Unsupported DATABASE_URL format: $DatabaseUrl"
    }

    return @{
        User = $match.Groups["user"].Value
        Password = $match.Groups["password"].Value
        Host = $match.Groups["host"].Value
        Port = $match.Groups["port"].Value
        Database = $match.Groups["database"].Value
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$venvPython = Join-Path $appRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment missing: $venvPython"
}

$databaseUrl = [string]($env:DATABASE_URL)
if (-not $databaseUrl) {
    $databaseUrl = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/auto_news_studio"
}
$stateBackend = [string]($env:STATE_BACKEND)
if (-not $stateBackend) {
    $stateBackend = "dual_write"
}

$parts = Parse-DatabaseUrl -DatabaseUrl $databaseUrl
$psql = Get-PsqlPath -AppRoot $appRoot

$env:DATABASE_URL = $databaseUrl
$env:STATE_BACKEND = $stateBackend
$env:PGPASSWORD = $parts.Password

$exists = & $psql -h $parts.Host -p $parts.Port -U $parts.User -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$($parts.Database)';"
if (-not [string]::IsNullOrWhiteSpace($exists)) {
    Write-Host "[INFO] Database '$($parts.Database)' already exists."
} else {
    Write-Host "[INFO] Creating database '$($parts.Database)'..."
    & $psql -h $parts.Host -p $parts.Port -U $parts.User -d postgres -c "CREATE DATABASE $($parts.Database);"
}

Write-Host "[INFO] Running Alembic migrations..."
& $venvPython -m alembic upgrade head

Write-Host "[INFO] Initializing schema..."
& $venvPython scripts\init_postgres.py

Write-Host "[INFO] Backfilling current ingest chain..."
& $venvPython scripts\backfill_ingest_chain.py

Write-Host "[INFO] Backfilling content assets..."
& $venvPython scripts\backfill_content_assets.py

Write-Host "[INFO] Verifying row counts..."
@'
from sqlalchemy import create_engine, text
import os

engine = create_engine(os.environ["DATABASE_URL"])
tables = [
    "source_connectors",
    "raw_items",
    "discovery_items_current",
    "intel_events_current",
    "event_snapshots",
    "intel_alerts_current",
    "intel_event_history",
    "intel_alert_history",
    "deep_dive_records",
    "deep_dive_documents",
    "brief_records",
]
with engine.connect() as conn:
    for table in tables:
        count = conn.execute(text(f"select count(*) from {table}")).scalar_one()
        print(f"{table}: {count}")
'@ | & $venvPython -

Write-Host "[OK] PostgreSQL bootstrap completed."
