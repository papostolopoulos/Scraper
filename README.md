# Job Miner – Repository Overview

This repository contains a FastAPI backend for multi-source job ingestion and scoring, plus a minimal static UI (`index.html`). See `scraper/README.md` for the full package documentation and developer notes.

## Quick start
- Backend (local): launch the API server
  - Python 3.11+ recommended; create a venv and install deps
  - Run the app using your venv interpreter (Windows PowerShell):
    - `.\.venv\Scripts\python.exe -m uvicorn scraper.web.server:app --reload`
  - If you see "Form data requires python-multipart", make sure dependencies are installed in the same environment you’re using to run uvicorn. From the repo root:
    - `pip install -e .`
- UI: open `index.html` in a browser and set the API Base if not `http://127.0.0.1:8000`.

VS Code tasks are included for quick testing and pipeline runs (`.vscode/tasks.json`).

## Observability
- Health summary endpoint: `GET /api/health/summary` returns recent run averages, the latest run, and anomaly heuristics (fetch spike, zero-jobs streak, high error rate).
- Metrics endpoint: `GET /api/metrics` surfaces operational counts, average phase timings, and a short event tail. A daily snapshot writer appends JSONL for trend analysis.
- UI health badge: the static UI polls `/api/health/summary` every 30s and shows a small badge (OK/Warnings/Issues) with a details panel.

For the detailed runbook (env vars, snapshots, troubleshooting), see `docs/observability.md`.

## Performance & Feature Flags
The scoring and enrichment pipeline can be tuned at runtime via environment variables (set before launching uvicorn):

- JOBMINER_HARD_JOB_CAP: Hard upper bound on number of jobs processed in a run (applied after fetch, before scoring). Example: `set JOBMINER_HARD_JOB_CAP=50`.
- JOBMINER_SCORE_WORKERS: Parallel workers for skill extraction / scoring (caps at 8). Increase gradually; IO + CPU mixed workload. Example: `set JOBMINER_SCORE_WORKERS=4`.
- JOBMINER_DISABLE_SEMANTIC=1: Disable semantic enrichment (alias to legacy SCRAPER_NO_SEMANTIC=1) for faster runs / offline usage.
- JOBMINER_FALLBACK_ENABLED=0: Disable secondary provider fetch when the primary returns zero jobs.
- JOBMINER_MAX_PAGES / JOBMINER_RESULTS_PER_PAGE: Override dynamic fetch sizing heuristics.
- JOBMINER_TOKEN_TTL_MINUTES: Adjust artifact download availability window (default 60).

Legacy equivalents still honored: SCRAPER_MAX_WORKERS, SCRAPER_NO_SEMANTIC, SCRAPER_SEMANTIC_ENABLE.

Example (Windows PowerShell):
```
$env:JOBMINER_SCORE_WORKERS="4"; $env:JOBMINER_HARD_JOB_CAP="50"; $env:JOBMINER_DISABLE_SEMANTIC="1"; .\.venv\Scripts\python.exe -m uvicorn scraper.web.server:app --reload
```
