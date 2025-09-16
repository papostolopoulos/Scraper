Param(
    [switch]$Fix
)

Write-Host "Running Ruff lint..." -ForegroundColor Cyan
if ($Fix) {
    python -m ruff check . --fix
} else {
    python -m ruff check .
}

Write-Host "Running Ruff format (check only) ..." -ForegroundColor Cyan
if ($Fix) {
    python -m ruff format .
} else {
    python -m ruff format . --check
}

Write-Host "Running mypy..." -ForegroundColor Cyan
python -m mypy scraper/jobminer || exit $LASTEXITCODE

Write-Host "All checks complete." -ForegroundColor Green