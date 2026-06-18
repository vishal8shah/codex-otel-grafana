param(
    [string]$GrafanaUrl = "http://localhost:3000",
    [string]$ContainerName = "codex-otel-lgtm",
    [string]$CodexConfigPath = (Join-Path $HOME ".codex\config.toml"),
    [switch]$Strict
)

$ErrorActionPreference = "Continue"
$script:Failures = 0

function Write-Check(
    [string]$Name,
    [bool]$Passed,
    [string]$Detail,
    [bool]$Required = $true
) {
    $state = if ($Passed) { "PASS" } elseif ($Required) { "FAIL" } else { "INFO" }
    if (-not $Passed -and $Required) { $script:Failures++ }
    Write-Host ("[{0}] {1}: {2}" -f $state, $Name, $Detail)
}

function Test-TcpPort([string]$HostName, [int]$Port) {
    try {
        $client = [Net.Sockets.TcpClient]::new()
        $task = $client.ConnectAsync($HostName, $Port)
        if (-not $task.Wait(2000)) { $client.Dispose(); return $false }
        $ok = $client.Connected
        $client.Dispose()
        return $ok
    } catch { return $false }
}

Write-Host "Codex Observability Kit doctor (connectivity and setup health only)"
Write-Host "This command does not discover telemetry schema or validate metric emission.`n"

$docker = Get-Command docker -ErrorAction SilentlyContinue
Write-Check "Docker CLI" ([bool]$docker) $(if ($docker) { $docker.Source } else { "not found on PATH" })

$dockerRunning = $false
if ($docker) {
    & docker info *> $null
    $dockerRunning = ($LASTEXITCODE -eq 0)
}
Write-Check "Docker engine" $dockerRunning $(if ($dockerRunning) { "reachable" } else { "not reachable" })

$containerRunning = $false
if ($dockerRunning) {
    $running = & docker ps --filter "name=^/$ContainerName$" --format "{{.Names}}" 2>$null
    $containerRunning = ($running -contains $ContainerName)
}
Write-Check "LGTM container" $containerRunning $(if ($containerRunning) { "running: $ContainerName" } else { "not running: $ContainerName" })

$grafanaReachable = $false
try {
    $health = Invoke-RestMethod -Uri "$GrafanaUrl/api/health" -TimeoutSec 3
    $grafanaReachable = ($health.database -eq "ok")
} catch {}
Write-Check "Grafana" $grafanaReachable $GrafanaUrl

$otlpHttp = Test-TcpPort "localhost" 4318
Write-Check "OTLP HTTP port" $otlpHttp "localhost:4318"
$otlpGrpc = Test-TcpPort "localhost" 4317
Write-Check "OTLP gRPC port" $otlpGrpc "localhost:4317"

$codex = Get-Command codex -ErrorAction SilentlyContinue
$codexVersion = if ($codex) { & codex --version 2>$null } else { $null }
$codexRunnable = [bool]$codex -and ($LASTEXITCODE -eq 0)
$codexDetail = if ($codexVersion) { $codexVersion } elseif ($codex) { $codex.Source } else { "not found on PATH" }
Write-Check "Codex CLI" $codexRunnable $codexDetail $Strict.IsPresent

Write-Check "User Codex config" (Test-Path $CodexConfigPath) $CodexConfigPath $Strict.IsPresent

Write-Host "`nStack health determines the default exit code. Use -Strict to require Codex CLI and config readiness."
Write-Host "Run schema-verify separately for discovery guidance."
if ($script:Failures -gt 0) { exit 1 }
