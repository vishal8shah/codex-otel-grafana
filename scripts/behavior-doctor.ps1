param([Parameter(ValueFromRemainingArguments = $true)][string[]]$PassThroughArgs)
$ErrorActionPreference = "Stop"
$python = Join-Path $env:LOCALAPPDATA "Python\bin\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $python) { Write-Error "Python 3.10 or newer is required."; exit 1 }
$script = Join-Path (Split-Path -Parent $PSScriptRoot) "tools\agent-behavior\behavior_doctor.py"
& $python $script @PassThroughArgs
exit $LASTEXITCODE
