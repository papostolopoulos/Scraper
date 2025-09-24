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
