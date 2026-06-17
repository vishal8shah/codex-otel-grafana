param(
    [string]$ContainerName = "codex-otel-lgtm",
    [string]$Image = "grafana/otel-lgtm:latest",
    [string]$OtelCollectorConfig = "$PSScriptRoot\otelcol-config.yaml",
    [switch]$Pull
)

$ErrorActionPreference = "Stop"

function Get-DockerCommand {
    $command = Get-Command docker -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $defaultPath = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
    if (Test-Path $defaultPath) {
        return $defaultPath
    }

    return $null
}

$Docker = Get-DockerCommand

if (-not $Docker) {
    throw "Docker CLI was not found. Install Docker Desktop first, then reopen PowerShell."
}

if ($Pull) {
    & $Docker pull $Image
}

$existing = & $Docker ps -a --filter "name=^/$ContainerName$" --format "{{.Names}}"

if ($existing -eq $ContainerName) {
    $isRunning = & $Docker inspect -f "{{.State.Running}}" $ContainerName
    if ($isRunning -eq "true") {
        Write-Host "Container '$ContainerName' is already running."
    } else {
        & $Docker start $ContainerName | Out-Null
        Write-Host "Started existing container '$ContainerName'."
    }
} else {
    $dockerArgs = @(
        "run",
        "--detach",
        "--name", $ContainerName,
        "--publish", "3000:3000",
        "--publish", "4317:4317",
        "--publish", "4318:4318",
        "--volume", "codex-otel-lgtm-data:/data",
        "--env", "ENABLE_LOGS_OTELCOL=1",
        "--env", "ENABLE_LOGS_GRAFANA=1"
    )

    if ($OtelCollectorConfig -and (Test-Path $OtelCollectorConfig)) {
        $resolvedConfig = (Resolve-Path $OtelCollectorConfig).Path
        $dockerArgs += @("--volume", "${resolvedConfig}:/otel-lgtm/otelcol-config.yaml:ro")
        Write-Host "Using OpenTelemetry Collector config: $resolvedConfig"
    }

    $dockerArgs += $Image

    & $Docker @dockerArgs | Out-Null

    Write-Host "Created and started container '$ContainerName'."
}

Start-Sleep -Seconds 3

& $Docker ps --filter "name=^/$ContainerName$" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

Write-Host ""
Write-Host "Grafana:   http://localhost:3000"
Write-Host "OTLP HTTP: http://localhost:4318"
Write-Host "OTLP gRPC: localhost:4317"
Write-Host "Login:     admin / admin"
