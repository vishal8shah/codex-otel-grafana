param(
    [switch]$Pull
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $RepoRoot "docker-compose.yml"
$composeArgs = @("compose", "--project-directory", $RepoRoot, "-f", $ComposeFile)

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Install and start Docker Desktop or Docker Engine first."
}

if ($Pull) {
    & docker @composeArgs pull
    if ($LASTEXITCODE -ne 0) { throw "docker compose pull failed with exit code $LASTEXITCODE." }
}

& docker @composeArgs up --detach
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed with exit code $LASTEXITCODE." }

& docker @composeArgs ps
if ($LASTEXITCODE -ne 0) { throw "docker compose ps failed with exit code $LASTEXITCODE." }

Write-Host ""
Write-Host "LGTM is bound to 127.0.0.1 only. Port overrides can be set in a local .env file."
Write-Host "Run scripts/doctor.ps1, then use interactive 'codex' for telemetry validation."
