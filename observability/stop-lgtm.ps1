param(
    [string]$ContainerName = "codex-otel-lgtm",
    [switch]$Remove
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
    throw "Docker CLI was not found."
}

$existing = & $Docker ps -a --filter "name=^/$ContainerName$" --format "{{.Names}}"

if ($existing -ne $ContainerName) {
    Write-Host "Container '$ContainerName' does not exist."
    exit 0
}

$isRunning = & $Docker inspect -f "{{.State.Running}}" $ContainerName
if ($isRunning -eq "true") {
    & $Docker stop $ContainerName | Out-Null
    Write-Host "Stopped container '$ContainerName'."
} else {
    Write-Host "Container '$ContainerName' is already stopped."
}

if ($Remove) {
    & $Docker rm $ContainerName | Out-Null
    Write-Host "Removed container '$ContainerName'."
    Write-Host "Persistent data volume 'codex-otel-lgtm-data' was left in place."
}
