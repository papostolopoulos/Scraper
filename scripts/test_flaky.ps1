Param(
  [int]$Reruns = 2,
  [int]$Delay = 1,
  [string]$Keyword = ""
)

if (-not (Test-Path .\.venv\Scripts\python.exe)) {
  Write-Host "Virtual env not found (.venv)." -ForegroundColor Yellow
  exit 1
}

$env:SCRAPER_DISABLE_FILE_LOGS = '1'
$env:SCRAPER_DISABLE_EVENTS = '1'

$k = "flaky"
if ($Keyword) { $k = "($Keyword) and flaky" }

Write-Host "Running flaky tests (filter: $k) with $Reruns reruns (delay $Delay s)" -ForegroundColor Cyan
 .\.venv\Scripts\python -m pytest -m flaky -k "$k" --reruns $Reruns --reruns-delay $Delay -q --maxfail=1
exit $LASTEXITCODE