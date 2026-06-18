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

$composeConfig = & docker @composeArgs config --format json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "docker compose config failed with exit code $LASTEXITCODE." }
$ContainerName = $composeConfig.services.lgtm.container_name
$ComposeProject = $composeConfig.name
$existingId = & docker ps -aq --filter "name=^/$ContainerName$"
if ($LASTEXITCODE -ne 0) { throw "Could not inspect existing Docker containers." }

if ($existingId) {
    $existingJson = & docker inspect $ContainerName
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect container '$ContainerName'." }
    $existing = ($existingJson | ConvertFrom-Json)[0]
    $existingProject = $existing.Config.Labels.'com.docker.compose.project'
    if (-not $existingProject) {
        $dataVolume = $existing.Mounts | Where-Object { $_.Destination -eq "/data" } | Select-Object -First 1
        $isLegacyLgtm = $existing.Config.Image -like "grafana/otel-lgtm:*" -and
            $dataVolume.Type -eq "volume" -and $dataVolume.Name -eq "codex-otel-lgtm-data"
        if (-not $isLegacyLgtm) {
            throw "Container '$ContainerName' already exists and is not a recognized legacy LGTM container."
        }

        Write-Host "Migrating legacy LGTM container '$ContainerName' to Docker Compose; preserving volume '$($dataVolume.Name)'."
        & docker rm --force $ContainerName | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not remove legacy container '$ContainerName'." }
    } elseif ($existingProject -ne $ComposeProject) {
        throw "Container '$ContainerName' belongs to Compose project '$existingProject', not '$ComposeProject'."
    }
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
