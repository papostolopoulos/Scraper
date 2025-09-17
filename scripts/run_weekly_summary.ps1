# Runs the weekly summary to produce a Markdown report.
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

    Write-Host "[weekly] Generating weekly summary..."
    & $python "scraper/scripts/weekly_summary.py"

    Write-Host "[weekly] Done."
}
catch {
    Write-Error $_
    exit 1
}
finally {
    Pop-Location | Out-Null
}