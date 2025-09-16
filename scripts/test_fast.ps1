Param(
  [string]$Pattern = "",
  [switch]$IncludeSlow
)

if (-not (Test-Path .\.venv\Scripts\python.exe)) {
  Write-Host "Virtual env not found (.venv)." -ForegroundColor Yellow
  exit 1
}

$env:SCRAPER_DISABLE_FILE_LOGS = '1'
$env:SCRAPER_DISABLE_EVENTS = '1'
$env:SCRAPER_FAST_TEST = '1'

$k = 'not slow'
if ($IncludeSlow) { $k = $Pattern }
elseif ($Pattern) { $k = "$Pattern and not slow" }

Write-Host "Running fast tests (pattern: $k)" -ForegroundColor Cyan
 .\.venv\Scripts\python -m pytest -q --timeout=40 -k "$k" --maxfail=1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Fast tests passed" -ForegroundColor Green