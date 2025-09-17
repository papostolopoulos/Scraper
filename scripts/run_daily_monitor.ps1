# Runs the daily snapshot followed by dashboard generation.
# - Detects and prefers local venv Python.
# - Runs from the repository root to keep relative paths stable.

param()

$ErrorActionPreference = 'Stop'

function Get-PythonExe {
    param([string]$RepoRoot)
    $venvPy = Join-Path $RepoRoot ".venv/Scripts/python.exe"
    if (Test-Path $venvPy) { return $venvPy }
    return "python"
}

try {
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    $python = Get-PythonExe -RepoRoot $repoRoot

    Push-Location $repoRoot

    Write-Host "[daily] Running daily snapshot..."
    & $python "scraper/scripts/daily_snapshot.py"

    Write-Host "[daily] Generating dashboard..."
    & $python "scraper/scripts/generate_dashboard.py"

    Write-Host "[daily] Done."
}
catch {
    Write-Error $_
    exit 1
}
finally {
    Pop-Location | Out-Null
}