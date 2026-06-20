$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Preflight = Join-Path $PSScriptRoot "preflight.py"
$py = Get-Command py -ErrorAction SilentlyContinue
$python = Get-Command python -ErrorAction SilentlyContinue

if ($py) {
    & py -3 --version
    if ($LASTEXITCODE -ne 0) { throw "The Python launcher exists, but Python 3 is unavailable." }
    & py -3 $Preflight
    exit $LASTEXITCODE
}

if ($python) {
    & python --version
    if ($LASTEXITCODE -ne 0) { throw "Python exists on PATH but could not run." }
    & python $Preflight
    exit $LASTEXITCODE
}

throw "Python was not found. Install Python 3.10 or newer without requiring administrator access, then rerun .\scripts\preflight.ps1."
