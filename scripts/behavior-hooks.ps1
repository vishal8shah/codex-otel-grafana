param([Parameter(Mandatory=$true,Position=0)][ValidateSet("install","check","remove")][string]$Action,[Parameter(ValueFromRemainingArguments = $true)][string[]]$PassThroughArgs)
$ErrorActionPreference = "Stop"
$python = Join-Path $env:LOCALAPPDATA "Python\bin\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $python) { Write-Error "Python 3.10 or newer is required."; exit 1 }
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $root "tools\agent-behavior\behavior_hooks.py"
& $python $script $Action --root $root @PassThroughArgs
exit $LASTEXITCODE
