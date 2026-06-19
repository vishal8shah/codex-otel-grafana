param(
    [switch]$EmitDerived,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PassThroughArgs
)

$ErrorActionPreference = "Stop"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "Python 3.10 or newer is required. Install Python and ensure 'python' is on PATH."
    exit 1
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$analyzer = Join-Path $repoRoot "tools\tool-failure\tool_failure.py"
$mode = if ($EmitDerived) { "--emit-derived" } else { "--dry-run" }
& $python.Source $analyzer $mode @PassThroughArgs
exit $LASTEXITCODE
