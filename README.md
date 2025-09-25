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

### Async Job API (Primary Workflow)
The preferred path for running a search + scoring pipeline is the async jobs interface:

1. `POST /api/jobs` (multipart/form-data) – starts a job. Required fields:
   - `resume` (PDF/DOC/DOCX file upload)
   - `title`, `location`, `distance` (int km)
   - Optional: `date_posted`, `work_mode`, `employment_type`, `salary`, `limit` (1–100), `country`, `app_id`, `app_key`
   Returns: `{ job_id, status }` immediately (status will usually be `fetching`).
2. `GET /api/jobs/{job_id}` – poll for status & progress every ~1s.
   Response fields:
  - `status`: one of `fetching | scoring | exporting | done | error | cancelled`
   - `timings`: phase timing accumulators (`fetch_sec`, `scoring_sec`, `export_sec`) plus dynamic `progress_extract` / `progress_score` objects when scoring is underway:
     ```json
     {
       "progress_extract": {"processed": 37, "total": 80},
       "progress_score": {"processed": 12, "total": 80}
     }
     ```
   - `count`: number of fetched (post‑dedupe) jobs considered for scoring
   - `limit`: hard cap applied
   - `token`: present only after `status=='done'` (use for CSV download)
3. `GET /api/jobs/{job_id}/download` – returns slim CSV (HTTP 400 if not yet done, 404 if purged/unknown). Use after token appears or immediately hit the endpoint (it will enforce readiness).
4. `POST /api/jobs/{job_id}/cancel` – cooperative cancellation. Marks job cancelled; pipeline halts between phases or mid-scoring batch. Cancelled jobs never expose a token.

Legacy synchronous path: `POST /api/prepare` still exists and returns a `token` directly when work completes inline, but it blocks the HTTP request and lacks incremental progress. Prefer the async trio above.

### Useful Monitoring & Support Endpoints
- `GET /api/metrics` – rolling process metrics (timings averages, recent event ring buffer, merge stats).
- `GET /api/health/summary` – high level health, merge effectiveness series & anomalies.
  - Anomaly types currently: `fetch_sec_spike`, `zero_jobs_streak`, `error_rate_high`, `merge_effectiveness_drop`, `merge_effectiveness_sustained_low`.
- `GET /api/skill_gaps` – emitted after a successful run if shortlist + gaps available.
- `GET /api/skill_recommendations?limit=25` – enrichment & adaptive ranking data.
- `GET /api/skill_progress` / `POST /api/skill_progress` – learning progression tracking.
- `GET /api/skill_progress/metrics?weeks=8` – time series for velocity sparkline.
- `GET /api/download?token=...` – legacy direct token download (parallel to async flow; new async flow wraps via `jobs/{id}/download`).

### Weekly Summary Script
Script: `python scripts/weekly_summary.py --days 7`

Reads `snapshots/runs.jsonl` (written automatically after each async job completes) and generates `snapshots/weekly/<ISO_YEAR>-<ISO_WEEK>.md` containing:
- Run counts (total/success/errors/zero-result)
- Average phase timings (fetch/scoring/export/total)
- Merge effectiveness stats (median/avg/latest/min/max)
- Top query titles
- Table of last 20 runs (ts, status, count/limit, fetch_sec, total_sec, effectiveness)
 - (If present) provenance diversity summary can be appended by running the provenance script below first.

Commit or publish this markdown weekly for historical baseline & anomaly reviews. Integrate with CI cron or GitHub Actions for automation.

### Web UI Progress Bar
The static `index.html` uses the async job endpoints to show a dynamic progress bar:
- Polls `GET /api/jobs/{id}` ~ every 900ms.
- Computes phase percentage from `progress_extract` & `progress_score` markers plus job status transitions (fetching → scoring → exporting → done).
- ETA heuristic blends a local exponential moving average of prior phase durations (persisted in `localStorage` under `jm_phase_avg`).
- Phase label displays counters (e.g., `extract 23/80`, then `score 10/80`).

Client Progress Heuristic (simplified):
```
if status==fetching: pct≈8%
elif scoring: pct = 10% + (extract_processed/total * 45%) + (score_processed/total * 35%)
elif exporting: pct≈92%
elif done/error: pct=100%
```

If your pipeline adds new phases, emit additional `progress_<phase>` timing objects or adjust the weighting logic in `index.html` to keep UX consistent.

### Provenance Diversity Script
Analyze how many distinct sources contribute to merged jobs over time (helps detect source dominance regressions).

Run:
```
python scripts/provenance_diversity.py --runs snapshots/runs.jsonl --out snapshots/provenance_diversity.json
```
Output JSON fields:
- `samples`: number of snapshot lines with a resolvable `provenance_count`.
- `buckets`: raw counts for provenance_count of 1,2,3,4+.
- `percentages`: bucket percentages.
- `median_provenance_count`: central tendency signal.

Add a short markdown excerpt (optional) to weekly summary by reading that JSON and appending a section; automation can be added later.

For the detailed runbook (env vars, snapshots, troubleshooting), see `docs/observability.md`.

## Performance & Feature Flags
The scoring and enrichment pipeline can be tuned at runtime via environment variables (set before launching uvicorn):

- JOBMINER_HARD_JOB_CAP: Hard upper bound on number of jobs processed in a run (applied after fetch, before scoring). Example: `set JOBMINER_HARD_JOB_CAP=50`.
- JOBMINER_SCORE_WORKERS: Parallel workers for skill extraction / scoring (caps at 8). Increase gradually; IO + CPU mixed workload. Example: `set JOBMINER_SCORE_WORKERS=4`.
- JOBMINER_DISABLE_SEMANTIC=1: Disable semantic enrichment (alias to legacy SCRAPER_NO_SEMANTIC=1) for faster runs / offline usage.
- JOBMINER_FALLBACK_ENABLED=0: Disable secondary provider fetch when the primary returns zero jobs.
- JOBMINER_MAX_PAGES / JOBMINER_RESULTS_PER_PAGE: Override dynamic fetch sizing heuristics.
- JOBMINER_TOKEN_TTL_MINUTES: Adjust artifact download availability window (default 60).
- Multi-source (Phase 1 ATS boards):
  - JOBMINER_ENABLE_GREENHOUSE=1 / JOBMINER_ENABLE_LEVER=1: Toggle ATS board fetching.
  - JOBMINER_GH_SLUGS="slug1,slug2" / JOBMINER_LEVER_SLUGS="slugA,slugB": Company board slugs.
  - JOBMINER_ATS_TITLE_OVERLAP=0.35: Min query title token overlap ratio to include an ATS posting.
  - JOBMINER_MAX_ATS_PER_SLUG=50: Per-slug cap to constrain requests & memory.
 - Multi-source (Phase 2 merge & enrichment):
   - JOBMINER_ENABLE_PHASE2_MERGE=1: Enable cross-source duplicate clustering + field backfill (default on).
   - JOBMINER_DEDUPE_PRIMARY=adzuna: Primary breadth source name (leads provenance ordering if present).
   - JOBMINER_DEDUPE_ORDER_PRIMARY_FIRST=1: When enabled (default), merged list ordered with primary-source jobs first.
   - Behavior: clusters postings by signature (apply URL host/path for non-generic hosts; else company+title+location), selects canonical (earliest posted_at → longer description), backfills salary/description fields, unions provenance.

Legacy equivalents still honored: SCRAPER_MAX_WORKERS, SCRAPER_NO_SEMANTIC, SCRAPER_SEMANTIC_ENABLE.

Example (Windows PowerShell):
```
$env:JOBMINER_SCORE_WORKERS="4"; $env:JOBMINER_HARD_JOB_CAP="50"; $env:JOBMINER_DISABLE_SEMANTIC="1"; .\.venv\Scripts\python.exe -m uvicorn scraper.web.server:app --reload
```

## Persistence & Temporary Artifacts
Runtime artifacts are stored under a configurable temp root (default: system temp + `jobminer_artifacts/`). Override with `JOBMINER_TMP_DIR`.

Structure:
- jobs/ <job_id>.json: Minimal job state snapshots (status, timings, token) enabling polling continuity after `--reload`.
- <token>.csv: Exported slim CSV results (one per completed job until TTL expiry).
- tokens_state.json: Metadata (creation times) for active tokens (CSV may be lazily reloaded from disk).
- snapshots/runs.jsonl: Append-only run snapshot lines (latest job status+timings) powering `/api/health/summary`.

Cleanup & Retention:
- Token & job retention aligned with token TTL (`JOBMINER_TOKEN_TTL_MINUTES`, default 60) — expired tokens are purged with their CSV.
- Snapshot file is opportunistically pruned (oldest lines truncated) to stay within configured line/age limits.
- Safe manual cleanup: stop the server, delete the TMP_DIR contents (NOT the main `scraper/data` DB) to reclaim space. Active jobs will lose progress if removed mid-run.

Recommended Production Hardening (future):
- Periodic cron to prune stale artifacts beyond TTL.
- Disk usage monitoring if large parallel runs anticipated.
- Optional migration to a persistent volume or S3 for longer artifact retention.
