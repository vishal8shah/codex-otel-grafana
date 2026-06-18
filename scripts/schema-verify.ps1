param(
    [string]$GrafanaUrl = "http://localhost:3000",
    [string]$CodexConfigPath = (Join-Path $HOME ".codex\config.toml")
)

$ErrorActionPreference = "Continue"

Write-Host "Codex OTel schema verification assistant"
Write-Warning "Interactive 'codex' is required for full metrics verification."
Write-Warning "Do not use 'codex exec' for metrics discovery; it can produce a false negative."
Write-Warning "'codex mcp-server' is currently not observable through Codex OTel."
Write-Host "This script checks prerequisites and prints query hints. It does not claim that a signal exists or is absent.`n"

$powerShellExe = (Get-Process -Id $PID).Path
& $powerShellExe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "doctor.ps1") -GrafanaUrl $GrafanaUrl -CodexConfigPath $CodexConfigPath
$doctorExit = $LASTEXITCODE
$configFailures = 0

Write-Host "`nUser-level OTel config checks: $CodexConfigPath"
if (Test-Path $CodexConfigPath) {
    $config = Get-Content -Raw $CodexConfigPath
    $otelMatch = [regex]::Match(
        $config,
        '(?ms)^\s*\[otel\]\s*(?<body>.*?)(?=^\s*\[[^\]]+\]\s*$|\z)'
    )
    if ($otelMatch.Success) {
        Write-Host "[PASS] [otel] section"
        $otelConfig = $otelMatch.Groups["body"].Value
    } else {
        Write-Host "[MISSING] [otel] section"
        $configFailures++
        $otelConfig = ""
    }

    $checks = [ordered]@{
        "exporter" = '(?m)^\s*exporter\s*='
        "metrics_exporter" = '(?m)^\s*metrics_exporter\s*='
        "trace_exporter" = '(?m)^\s*trace_exporter\s*='
        "log_user_prompt = false" = '(?m)^\s*log_user_prompt\s*=\s*false\s*(?:#.*)?$'
    }
    foreach ($item in $checks.GetEnumerator()) {
        $found = $otelConfig -match $item.Value
        $state = if ($found) { "PASS" } else { "MISSING" }
        if (-not $found) { $configFailures++ }
        Write-Host "[$state] $($item.Key)"
    }
} else {
    $configFailures++
    Write-Warning "Config file not found. Schema verification cannot proceed until user-level OTel is configured."
}

Write-Host @"

Manual discovery procedure:
1. Start an interactive session by running: codex
2. Submit a tiny, non-sensitive prompt manually.
3. Exercise a harmless tool path only if tool telemetry is under test.
4. Exit Codex cleanly so the OTel exporters can flush.
5. Wait briefly, then run the queries below in Grafana Explore.

Loki query hints (field existence must be confirmed from returned records):
  {service_name="Codex Desktop"} | event_name="codex.conversation_starts"
  {service_name="Codex Desktop"} | event_name="codex.sse_event"
  {service_name="Codex Desktop"} | event_name="codex.sse_event" | event_kind="response.completed"
  {service_name="Codex Desktop"} | event_name="codex.tool_decision"
  {service_name="Codex Desktop"} | event_name="codex.tool_result"

Prometheus candidate hints (OTLP names may be normalized; verify every stored
name through the metric browser before recording it as observed):
  {__name__=~"codex_(api_request|sse_event|websocket_request|websocket_event|tool_call).*"}
  codex_api_request_total
  codex_api_request_duration_ms_bucket
  codex_sse_event_total
  codex_sse_event_duration_ms_bucket
  codex_websocket_request_total
  codex_websocket_request_duration_ms_bucket
  codex_websocket_event_total
  codex_websocket_event_duration_ms_bucket
  codex_tool_call_total
  codex_tool_call_duration_ms_bucket

Tempo TraceQL query hints:
  { resource.service.name = "Codex Desktop" }
  { resource.service.name = "Codex Desktop" && name = "codex.tool.call" }

Structured log terms to verify, not assume:
  codex.conversation_starts, codex.sse_event, response.completed,
  codex.tool_decision, codex.tool_result

Native metric families to verify, not assume:
  codex.api_request, codex.api_request.duration_ms, codex.sse_event,
  codex.sse_event.duration_ms, codex.websocket.request,
  codex.websocket.request.duration_ms, codex.websocket.event,
  codex.websocket.event.duration_ms, codex.tool.call,
  codex.tool.call.duration_ms

Record sanitized evidence manually in SCHEMA.md. A metrics result obtained with
'codex exec' is invalid for full schema verification.
"@

if ($doctorExit -ne 0 -or $configFailures -gt 0) { exit 1 }
