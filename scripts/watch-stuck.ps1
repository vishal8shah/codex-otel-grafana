param(
    [ValidateRange(15, 86400)]
    [int]$IntervalSeconds = 60,
    [switch]$EmitDerived,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PassThroughArgs
)

$ErrorActionPreference = "Stop"
$runHealth = Join-Path $PSScriptRoot "run-health.ps1"
$mode = if ($EmitDerived) { "emit-derived" } else { "dry-run" }

Write-Host "Codex stuck watcher: mode=$mode interval_seconds=$IntervalSeconds"
Write-Host "Press Ctrl+C to stop. The watcher is opt-in and is not started by the LGTM stack."

try {
    while ($true) {
        if ($EmitDerived) {
            & $runHealth -EmitDerived @PassThroughArgs
        } else {
            & $runHealth @PassThroughArgs
        }
        if ($LASTEXITCODE -ne 0) {
            throw "run-health analyzer exited with code $LASTEXITCODE."
        }
        Start-Sleep -Seconds $IntervalSeconds
    }
} finally {
    Write-Host "Codex stuck watcher stopped."
}
