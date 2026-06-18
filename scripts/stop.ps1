param(
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $RepoRoot "docker-compose.yml"
$composeArgs = @("compose", "--project-directory", $RepoRoot, "-f", $ComposeFile)

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found."
}

if ($Remove) {
    & docker @composeArgs down
    if ($LASTEXITCODE -ne 0) { throw "docker compose down failed with exit code $LASTEXITCODE." }
    Write-Host "Removed the Compose container and network. The named data volume was preserved."
} else {
    & docker @composeArgs stop
    if ($LASTEXITCODE -ne 0) { throw "docker compose stop failed with exit code $LASTEXITCODE." }
}
