# Job Miner – Repository Overview

This repository contains a FastAPI backend for multi-source job ingestion and scoring, plus a minimal static UI (`index.html`). See `scraper/README.md` for the full package documentation and developer notes.

## Quick start
- Backend (local): launch the API server
  - Python 3.11+ recommended; create a venv and install deps
  - Run the app: `python -m uvicorn scraper.web.server:app --reload`
- UI: open `index.html` in a browser and set the API Base if not `http://127.0.0.1:8000`.

VS Code tasks are included for quick testing and pipeline runs (`.vscode/tasks.json`).

## Observability
- Health summary endpoint: `GET /api/health/summary` returns recent run averages, the latest run, and anomaly heuristics (fetch spike, zero-jobs streak, high error rate).
- Metrics endpoint: `GET /api/metrics` surfaces operational counts, average phase timings, and a short event tail. A daily snapshot writer appends JSONL for trend analysis.
- UI health badge: the static UI polls `/api/health/summary` every 30s and shows a small badge (OK/Warnings/Issues) with a details panel.

For the detailed runbook (env vars, snapshots, troubleshooting), see `docs/observability.md`.
