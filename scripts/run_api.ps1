$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (Test-Path ".venv\Scripts\python.exe") {
    & .\.venv\Scripts\python.exe -m friday.main
} else {
    python -m friday.main
}

