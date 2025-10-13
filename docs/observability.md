# Observability & Runbook

This project exposes basic observability to make runs transparent and regressions obvious.

## Components
- Structured JSON logging middleware (backend): request/response duration, correlation, status.
- /api/metrics endpoint: aggregated timings, phase counts, recent event tail.
- Snapshot Writer: appends JSONL metrics snapshots with retention pruning.
- /api/health/summary: averages, latest, anomalies (fetch spike, zero-job streak, error rate heuristics).
- Skill progress persistence: `scraper/data/skill_progress.json` (updated atomically).

## Environment Variables
- SCRAPER_DISABLE_EVENTS=1: mute in-memory event ring buffer (optional).
- SCRAPER_DISABLE_FILE_LOGS=1: skip writing file logs (CI-friendly).
- SCRAPER_RUN_SUMMARY: override path/name for pipeline summary JSON (tests use this).
- SCRAPER_FORCE_HEADLESS=1: force headless browser in collectors.
- SCRAPER_ABORT_IF_LOGIN=1: abort collection if login is detected.
- JOBMINER_FUZZY_NORMALIZATION=1: enable fuzzy normalization in dedupe/signature.

## Snapshots
- Location: `snapshots/metrics-YYYY-MM-DD.jsonl` (one per day).
- Pruning: age- and line-based limits keep files bounded.
- Use Cases: trend dashboards, CI artifacts, regression analysis.

## Health Summary
- Endpoint: `/api/health/summary`
- Returns structured summary with averages and anomalies (spike/error-rate/zero-job streak).
- UI can show a small badge (OK/Warning) linking to a panel with details.

## Run Summary
- Pipeline writes `data/exports/pipeline_summary.json` (or `SCRAPER_RUN_SUMMARY`).
- Includes distribution stats, timing, and coverage (field presence) metrics.

## Runbook
1. If exports are empty or anomalies reported:
   - Check `/api/metrics` for phase timings and counts.
   - Inspect recent events (ring buffer) from logs.
   - Open latest `snapshots/metrics-*.jsonl` tail for trends.
2. Dedupe complaints or duplicates slipping through:
   - Verify `JOBMINER_FUZZY_NORMALIZATION` and `desc_prefix` settings.
   - Check similarity thresholds (Jaccard/title fuzzy).
3. Windows file errors writing progress:
   - Persistence uses atomic replace with retry; ensure working directory permissions.
4. Test runs:
   - Use VS Code tasks: "Run tests (quick)".
   - CI publishes coverage artifacts; see Actions tab.

## Anomaly thresholds & tuning
- Detector: `scraper/jobminer/anomaly.py` reads the latest run and compares against the mean of the previous N runs.
- Defaults: `recent_n = 5`, `drop_threshold_pct = 0.35` (i.e., trigger if current < 65% of baseline).
- Signals evaluated (when present in history JSONL):
  - `avg_score`: average composite score across processed jobs
  - `skills_per_job`: average number of extracted skills per job
- Data source: daily JSONL under `snapshots/metrics-YYYY-MM-DD.jsonl` (appended via Snapshot Writer) and run summaries via `scraper/jobminer/history.append_history`.

How to adjust (temporary triage):
1) Re-run detection with custom params (example from a Python REPL):
   - `from pathlib import Path; from scraper.jobminer.anomaly import detect_anomalies`
   - `detect_anomalies(Path('snapshots/metrics-2025-10-11.jsonl'), recent_n=7, drop_threshold_pct=0.45)`
2) Investigate baseline quality:
   - Ensure at least `recent_n` valid prior points exist; missing/None data will be skipped.
   - Confirm spikes weren’t caused by intentionally smaller runs (e.g., test mode with few jobs).
3) If noisy:
   - Increase `recent_n` to smooth variance or temporarily raise `drop_threshold_pct`.
   - Add more context in weekly summary for the affected days.

Where surfaced:
- `/api/health/summary` returns anomalies list consumed by UI and weekly reports.
- The weekly summary page highlights anomaly messages with drop percentages and baselines.
