from __future__ import annotations
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from pathlib import Path
from datetime import datetime, timezone, timedelta
import io
import csv
import uuid
import os
import tempfile
import re
import time
import threading
import concurrent.futures
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

# Internal imports
from scraper.jobminer.db import JobDB
from scraper.jobminer.pipeline import score_all
from scraper.jobminer.sources.base import normalize_ids
from scraper.jobminer.sources.adzuna_source import (
    AdzunaSource,
    AdzunaAuthError,
    AdzunaRateLimitError,
    AdzunaHTTPError,
    AdzunaNetworkError,
)
from scraper.jobminer.sources.remotive_source import RemotiveSource
from scraper.jobminer.exporter import Exporter
from scraper.jobminer.skill_recommendations import enrich_gap_skills
from scraper.jobminer.skill_progress import upsert_progress, list_progress, get_progress_for, compute_velocity_metrics
from scraper.jobminer.skill_dependencies import unresolved_prereqs, load_dependencies

app = FastAPI(title="Job Miner Web MVP")

# ---------------- Structured Logging & Events ----------------
import json as _json
JSON_LOGS_ENABLED = os.getenv("JOBMINER_JSON_LOGS", "1").lower() in ("1","true","yes","on")

# Retention configuration (defaults)
_SNAPSHOT_MAX_LINES_DEFAULT = 5000
_SNAPSHOT_MAX_AGE_DAYS_DEFAULT = 7

def _int_env(name: str, default: int) -> int:
    try:
        v = int(os.getenv(name, str(default)))
        return max(1, v)
    except Exception:
        return default

def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default

SNAPSHOT_MAX_LINES = _int_env("JOBMINER_SNAPSHOT_MAX_LINES", _SNAPSHOT_MAX_LINES_DEFAULT)
SNAPSHOT_MAX_AGE_DAYS = _int_env("JOBMINER_SNAPSHOT_MAX_AGE_DAYS", _SNAPSHOT_MAX_AGE_DAYS_DEFAULT)

# (Threshold envs will be read later in health summary for anomaly detection tuning)
ANOM_FETCH_SPIKE = _float_env("JOBMINER_ANOM_FETCH_SPIKE", 1.5)
ANOM_ERROR_RATE = _float_env("JOBMINER_ANOM_ERROR_RATE", 0.3)
ANOM_ZERO_JOBS_STREAK = _int_env("JOBMINER_ANOM_ZERO_JOBS_STREAK", 3)

def _json_log(**fields):
    if not JSON_LOGS_ENABLED:
        return
    try:
        base = {
            'ts': datetime.now(timezone.utc).isoformat(),
        }
        base.update(fields)
        print(_json.dumps(base, default=str), flush=True)
    except Exception:
        pass

EVENT_BUFFER_MAX = 200
EVENTS: list[dict] = []
EVENTS_LOCK = threading.Lock()

def log_event(kind: str, **payload):
    rec = {
        'kind': kind,
        'ts': datetime.now(timezone.utc).isoformat(),
    }
    rec.update(payload)
    with EVENTS_LOCK:
        EVENTS.append(rec)
        if len(EVENTS) > EVENT_BUFFER_MAX:
            del EVENTS[0:len(EVENTS)-EVENT_BUFFER_MAX]
    _json_log(event=kind, **payload)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):  # type: ignore
        start = time.perf_counter()
        path = request.url.path
        method = request.method
        req_id = uuid.uuid4().hex[:8]
        _json_log(msg='request_start', request_id=req_id, method=method, path=path)
        try:
            response = await call_next(request)
            status = getattr(response, 'status_code', None)
        except Exception as e:  # pragma: no cover
            dur = round((time.perf_counter() - start)*1000, 2)
            _json_log(msg='request_error', request_id=req_id, method=method, path=path, duration_ms=dur, error=str(e))
            raise
        dur = round((time.perf_counter() - start)*1000, 2)
        _json_log(msg='request_end', request_id=req_id, method=method, path=path, status=status, duration_ms=dur)
        return response

app.add_middleware(RequestLoggingMiddleware)

# Allow cross-origin requests from GitHub Pages (static hosting) and localhost
PAGES_ORIGIN = "https://papostolopoulos.github.io"
origins = [
    PAGES_ORIGIN,
    f"{PAGES_ORIGIN}/Scraper",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_default_tmp_root = Path(os.getenv("JOBMINER_TMP_DIR") or (Path(tempfile.gettempdir()) / "jobminer_artifacts"))
TMP_DIR = _default_tmp_root
TMP_DIR.mkdir(parents=True, exist_ok=True)

# In-memory registry mapping token -> {data: bytes | None, created: datetime}
TOKENS: dict[str, dict] = {}

# Simple persistence file so tokens survive reload cycles
TOKEN_STATE_FILE = TMP_DIR / "tokens_state.json"
def _load_tokens_state():
    if TOKEN_STATE_FILE.exists():
        try:
            import json as _json
            data = _json.loads(TOKEN_STATE_FILE.read_text(encoding="utf-8"))
            for k,v in list(data.items()):
                try:
                    created_raw = v.get('created')
                    if not created_raw:
                        continue
                    created = datetime.fromisoformat(created_raw)
                    # Only rehydrate if artifact file still valid (TTL check done later during download)
                    TOKENS.setdefault(k, {'data': None, 'created': created})
                except Exception:
                    continue
        except Exception:
            pass
_load_tokens_state()

# Simple in-memory rate limiting (global prepare endpoint)
LAST_CALLS: list[datetime] = []
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 12     # max prepare calls per window

# Per-IP download daily counters
DOWNLOAD_COUNTS: dict[str, dict] = {}
MAX_DOWNLOADS_PER_DAY = 3

# Configurable token TTL (default 60 minutes, override via env)
def _ttl_minutes():
    v = os.getenv("JOBMINER_TOKEN_TTL_MINUTES")
    if v and v.isdigit():
        return max(1, min(24*60, int(v)))  # cap at 24h
    return 60
TOKEN_TTL = timedelta(minutes=_ttl_minutes())

# ---------------- Job-based async pipeline ----------------
@dataclass
class JobRun:
    job_id: str
    created: datetime
    status: str = "queued"  # queued|fetching|scoring|exporting|done|error
    error: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    timings: Dict[str, float] = field(default_factory=dict)  # phase timings
    token: Optional[str] = None
    artifact_file: Optional[Path] = None
    count: int = 0
    limit: int = 0

JOBS: Dict[str, JobRun] = {}
JOBS_LOCK = threading.Lock()
EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=2)

def _register_job(j: JobRun):
    with JOBS_LOCK:
        JOBS[j.job_id] = j
    log_event('job_created', job_id=j.job_id, title=j.params.get('title'))

def _get_job(job_id: str) -> Optional[JobRun]:
    with JOBS_LOCK:
        return JOBS.get(job_id)

def _prune_jobs():
    now = datetime.now(timezone.utc)
    cutoff = now - TOKEN_TTL  # reuse TTL window for job retention
    remove = []
    with JOBS_LOCK:
        for jid, jr in JOBS.items():
            if jr.created < cutoff:
                remove.append(jid)
        for jid in remove:
            JOBS.pop(jid, None)
    # Remove orphan artifact directories? Artifacts are single csv files already handled by token pruning.

def _process_job(job: JobRun):
    """Background thread task to perform fetch->scoring->export, mirroring legacy /api/prepare."""
    t_total = time.perf_counter()
    try:
        params = job.params
        job.status = 'fetching'
        log_event('job_fetch_start', job_id=job.job_id)
        resume_path: Path = params['resume_path']
        title = params['title']
        location = params['location']
        distance = params['distance']
        limit = params['limit']
        app_id = params.get('app_id') or os.getenv("ADZUNA_APP_ID")
        app_key = params.get('app_key') or os.getenv("ADZUNA_APP_KEY")
        country = params.get('country', 'us')
        employment_type = params.get('employment_type')
        date_posted = params.get('date_posted')
        work_mode = params.get('work_mode')
        contract_time = None
        if employment_type:
            et = employment_type.lower().replace('-', '_')
            if et in ("full_time", "part_time"):
                contract_time = et
        max_days_old = None
        if date_posted:
            dp = str(date_posted).lower()
            max_days_old = {"1":1,"3":3,"7":7,"14":14,"30":30}.get(dp)
        target_limit = limit
        # Dynamic sizing with optional env overrides
        if target_limit <= 25:
            dyn_pages, dyn_per = 1, target_limit
        elif target_limit <= 50:
            dyn_pages, dyn_per = 2, (target_limit + 1)//2
        else:
            dyn_pages, dyn_per = 3, min(50, (target_limit + 2)//3)
        dyn_per = max(1, min(50, dyn_per))
        # Env overrides
        max_pages_env = os.getenv('JOBMINER_MAX_PAGES')
        rpp_env = os.getenv('JOBMINER_RESULTS_PER_PAGE')
        try:
            if max_pages_env and max_pages_env.isdigit():
                dyn_pages = max(1, min(10, int(max_pages_env)))
            if rpp_env and rpp_env.isdigit():
                dyn_per = max(1, min(50, int(rpp_env)))
        except Exception:
            pass
        if not (app_id and app_key):
            raise RuntimeError("Missing Adzuna credentials (supply app_id/app_key)" )
        src = AdzunaSource(
            name="adzuna", app_id=app_id, app_key=app_key, country=country.lower(),
            what=title, where=location, distance=int(distance), max_pages=dyn_pages,
            results_per_page=dyn_per, max_days_old=max_days_old, contract_time=contract_time,
        )
        t_fetch = time.perf_counter()
        jobs = src.fetch()
        jobs = normalize_ids(jobs, src.name)
        job.timings['fetch_sec'] = round(time.perf_counter() - t_fetch, 3)
        fb_enabled = os.getenv('JOBMINER_FALLBACK_ENABLED','1').lower() in ('1','true','yes','on')
        if fb_enabled and len(jobs) == 0:
            try:
                remotive = RemotiveSource(what=title)
                fb_jobs = remotive.fetch()
                if fb_jobs:
                    jobs.extend(normalize_ids(fb_jobs, remotive.name))
            except Exception:
                pass
        if work_mode and work_mode.lower() in ("remote","hybrid","onsite"):
            wm = work_mode.lower()
            jobs = [j for j in jobs if (j.work_mode or '').lower() == wm]
        if len(jobs) > limit:
            jobs = jobs[:limit]
        job.count = len(jobs)
        # DB + scoring
        job.status = 'scoring'
        log_event('job_scoring_start', job_id=job.job_id, fetched=job.count)
        db = JobDB()
        db.upsert_jobs(jobs)
        seed_path = Path("scraper/config/seed_skills.txt")
        if not seed_path.exists():
            import re as _re
            tokens = [t for t in _re.split(r"[^A-Za-z0-9+.#-]+", title) if t]
            seed_path.write_text("\n".join(tokens), encoding='utf-8')
        t_score = time.perf_counter()
        if jobs:
            def _progress_cb(phase, processed, total):
                job.count = total
                # We overload 'count' as total jobs; provide processed via timings map for now
                job.timings[f'progress_{phase}'] = {'processed': processed, 'total': total}
            score_all(db, resume_path, seed_path, write_summary=False, max_workers=1, progress_cb=_progress_cb)
        job.timings['scoring_sec'] = round(time.perf_counter() - t_score, 3)
        # Export
        job.status = 'exporting'
        log_event('job_export_start', job_id=job.job_id)
        export_dir = TMP_DIR / uuid.uuid4().hex
        exporter = Exporter(db, export_dir, stream=True)
        t_export = time.perf_counter()
        artifacts = exporter.export_all() or {}
        full_csv = artifacts.get('full_csv')
        out_rows = []
        if full_csv and Path(full_csv).exists():
            with open(full_csv, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                for i,row in enumerate(reader):
                    out_rows.append(row)
                    if i+1 >= limit:
                        break
        job.timings['export_sec'] = round(time.perf_counter() - t_export, 3)
        slim_cols = [
            'title','company_name','location','work_mode','employment_type','posted_at',
            'offered_salary_min','offered_salary_max','offered_salary_currency','salary_period','salary_is_predicted',
            'skill_score','skill_precision','skill_recall','skill_overlap_count','skill_core_size','semantic_score','score_total','matched_skills','apply_url','top_skills'
        ]
        if out_rows:
            buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=slim_cols); w.writeheader()
            for r in out_rows:
                row = {k:r.get(k) for k in slim_cols}
                if not row.get('top_skills'):
                    ms = r.get('matched_skills') or ''
                    if ms:
                        parts=[p.strip() for p in ms.split(',') if p.strip()][:5]
                        if parts: row['top_skills'] = ", ".join(parts)
                w.writerow(row)
            data = buf.getvalue().encode('utf-8')
        else:
            data = b"title\n"
        token = uuid.uuid4().hex
        created = datetime.now(timezone.utc)
        TOKENS[token] = {'data': data, 'created': created}
        try:
            file_path = TMP_DIR / f"{token}.csv"
            with open(file_path, 'wb') as fh: fh.write(data)
        except Exception: pass
        _prune_tokens()
        job.token = token
        job.artifact_file = file_path if 'file_path' in locals() else None
        job.status = 'done'
    except Exception as e:
        job.status = 'error'
        job.error = str(e)
        log_event('job_error', job_id=job.job_id, error=str(e))
    finally:
        job.timings['total_sec'] = round(time.perf_counter() - t_total, 3)
        if job.status == 'done':
            log_event('job_done', job_id=job.job_id, total_sec=job.timings['total_sec'])
        try:
            # Attempt cleanup of resume temp file
            rp = job.params.get('resume_path')
            if rp and Path(rp).exists():
                Path(rp).unlink(missing_ok=True)
        except Exception:
            pass
        # Persist snapshot (append JSON line) for health summary calculations
        try:
            snap_dir = TMP_DIR / 'snapshots'
            snap_dir.mkdir(parents=True, exist_ok=True)
            snap_file = snap_dir / 'runs.jsonl'
            record = {
                'ts': datetime.now(timezone.utc).isoformat(),
                'job_id': job.job_id,
                'status': job.status,
                'error': job.error,
                'count': job.count,
                'limit': job.limit,
                'timings': job.timings,
            }
            with open(snap_file, 'a', encoding='utf-8') as fh:
                fh.write(_json.dumps(record) + '\n')
            # Prune snapshot file to enforce retention limits
            _prune_snapshot_file(snap_file)
        except Exception:
            pass
        _prune_jobs()

@app.post('/api/jobs')
async def create_job(
    resume: UploadFile = File(...),
    title: str = Form(...),
    location: str = Form(...),
    distance: int = Form(...),
    date_posted: str | None = Form(None),
    work_mode: str | None = Form(None),
    employment_type: str | None = Form(None),
    salary: int | None = Form(None),
    limit: int | None = Form(50),
    country: str | None = Form("us"),
    app_id: str | None = Form(None),
    app_key: str | None = Form(None),
):
    # Validate inputs (reuse simplified rules)
    errs = []
    if not title: errs.append('title required')
    if not location: errs.append('location required')
    if distance is None or distance < 0 or distance > 250: errs.append('distance out of range (0-250)')
    allowed_ext={'.pdf','.doc','.docx'}; ext = Path(resume.filename or '').suffix.lower()
    if ext and ext not in allowed_ext: errs.append('unsupported resume type')
    if errs: raise HTTPException(status_code=400, detail=", ".join(errs))
    # Store resume temp
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext or '.pdf') as tf:
            content = await resume.read(); tf.write(content); resume_path = Path(tf.name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to store resume: {e}')
    try:
        lim = max(1, min(int(limit or 50), 100))
    except Exception:
        lim = 50
    job_id = uuid.uuid4().hex
    jr = JobRun(job_id=job_id, created=datetime.now(timezone.utc), params={
        'resume_path': resume_path,
        'title': title,
        'location': location,
        'distance': distance,
        'date_posted': date_posted,
        'work_mode': work_mode,
        'employment_type': employment_type,
        'salary': salary,
        'limit': lim,
        'country': country,
        'app_id': app_id,
        'app_key': app_key,
    }, limit=lim)
    _register_job(jr)
    # Submit to executor
    EXECUTOR.submit(_process_job, jr)
    return {'job_id': job_id, 'status': jr.status}

@app.get('/api/jobs/{job_id}')
def get_job(job_id: str):
    jr = _get_job(job_id)
    if not jr:
        raise HTTPException(status_code=404, detail='job not found')
    # Extract lightweight progress metrics
    progress = {}
    for k,v in jr.timings.items():
        if k.startswith('progress_'):
            phase = k.replace('progress_','')
            try:
                if isinstance(v, dict):
                    progress[phase] = v
            except Exception:
                pass
    return {
        'job_id': jr.job_id,
        'status': jr.status,
        'error': jr.error,
        'timings': jr.timings,
        'count': jr.count,
        'limit': jr.limit,
        'token': jr.token if jr.status == 'done' else None,
        'progress': progress or None,
    }

@app.get('/api/jobs/{job_id}/download')
def download_job(job_id: str):
    jr = _get_job(job_id)
    if not jr:
        raise HTTPException(status_code=404, detail='job not found')
    if jr.status != 'done' or not jr.token:
        raise HTTPException(status_code=400, detail='job not ready')
    # Reuse existing token download logic by delegating
    return StreamingResponse(io.BytesIO((TOKENS.get(jr.token) or {}).get('data') or (TMP_DIR / f"{jr.token}.csv").read_bytes()), media_type='text/csv', headers={
        'Content-Disposition': f'attachment; filename=job_results_{jr.token[:8]}.csv'
    })

def _prune_tokens():
    now = datetime.now(timezone.utc)
    expired = [k for k,v in TOKENS.items() if (now - v['created']) > TOKEN_TTL]
    for k in expired:
        TOKENS.pop(k, None)
        fp = TMP_DIR / f"{k}.csv"
        if fp.exists():
            try: fp.unlink()
            except Exception: pass
    # Persist surviving metadata (not blobs) to disk
    try:
        import json as _json
        serializable = {k:{'created': v['created'].isoformat()} for k,v in TOKENS.items()}
        TOKEN_STATE_FILE.write_text(_json.dumps(serializable), encoding="utf-8")
    except Exception:
        pass

def _rate_limited():
    now = datetime.now(timezone.utc)
    # remove old timestamps
    cutoff = now - timedelta(seconds=RATE_LIMIT_WINDOW)
    while LAST_CALLS and LAST_CALLS[0] < cutoff:
        LAST_CALLS.pop(0)
    if len(LAST_CALLS) >= RATE_LIMIT_MAX:
        return True
    LAST_CALLS.append(now)
    return False

def _check_download_limit(ip: str) -> bool:
    today = datetime.now(timezone.utc).date().isoformat()
    rec = DOWNLOAD_COUNTS.get(ip)
    if not rec or rec.get('day') != today:
        rec = {'day': today, 'count': 0}
        DOWNLOAD_COUNTS[ip] = rec
    if rec['count'] >= MAX_DOWNLOADS_PER_DAY:
        return False
    rec['count'] += 1
    return True

@app.get("/")
def root() -> HTMLResponse:
    html = Path("scraper/web/index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)

@app.post("/api/prepare")
async def prepare(
    resume: UploadFile = File(...),
    title: str = Form(...),
    location: str = Form(...),
    distance: int = Form(...),
    date_posted: str | None = Form(None),
    work_mode: str | None = Form(None),
    employment_type: str | None = Form(None),
    salary: int | None = Form(None),
    limit: int | None = Form(50),
    country: str | None = Form("us"),
    app_id: str | None = Form(None),
    app_key: str | None = Form(None),
):
    # Basic rate limiting
    if _rate_limited():
        raise HTTPException(status_code=429, detail="Too many requests, slow down and retry shortly")

    # Validate required fields
    errors = []
    if not title:
        errors.append("title required")
    if not location:
        errors.append("location required")
    if distance is None or distance < 0 or distance > 250:
        errors.append("distance must be between 0 and 250 miles")
    # File validation: extension & size (seekable stream may not expose size reliably until read)
    allowed_ext = {'.pdf','.doc','.docx'}
    ext = Path(resume.filename or '').suffix.lower()
    if ext and ext not in allowed_ext:
        errors.append("unsupported resume file type")
    # Peek at size
    try:
        resume.file.seek(0, os.SEEK_END)
        size = resume.file.tell()
        resume.file.seek(0)
        if size > 5 * 1024 * 1024:
            errors.append("resume file too large (max 5MB)")
    except Exception:
        pass
    if errors:
        raise HTTPException(status_code=400, detail=", ".join(errors))

    # Persist uploaded resume to a temp file; FastAPI UploadFile is a SpooledTemporaryFile
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(resume.filename or "resume").suffix or ".pdf") as tf:
            content = await resume.read()
            tf.write(content)
            tmp_resume_path = Path(tf.name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store resume: {e}")

    # Prepare DB and fetch jobs from Adzuna
    db = JobDB()  # uses default sqlite path under scraper/data
    timings: dict[str, float] = {}
    t_total_start = time.perf_counter()
    try:
        # Map web form to Adzuna params
        # Adzuna supports contract_time=full_time|part_time; we pass only when given
        contract_time = None
        if employment_type:
            et = employment_type.lower().replace('-', '_')
            if et in ("full_time", "part_time"):
                contract_time = et

        # Adzuna has max_days_old; map common date_posted choices
        max_days_old = None
        if date_posted:
            dp = str(date_posted).lower()
            max_days_old = {"1": 1, "3": 3, "7": 7, "14": 14, "30": 30}.get(dp)

        # Dynamic paging: tune requested pages and per-page to not greatly exceed user limit
        # Aim to fetch at most ~1.2x limit while minimizing API calls.
        target_limit = max(1, min(int(limit or 50), 100))
        if target_limit <= 25:
            dyn_pages, dyn_per = 1, target_limit
        elif target_limit <= 50:
            dyn_pages, dyn_per = 2, (target_limit + 1)//2
        else:
            dyn_pages, dyn_per = 3, min(50, (target_limit + 2)//3)
        dyn_per = max(1, min(50, dyn_per))

        src = AdzunaSource(
            name="adzuna",
            app_id=app_id or os.getenv("ADZUNA_APP_ID"),
            app_key=app_key or os.getenv("ADZUNA_APP_KEY"),
            country=(country or "us").lower(),
            what=title,
            where=location,
            distance=int(distance),
            max_pages=dyn_pages,
            results_per_page=dyn_per,
            max_days_old=max_days_old,
            contract_time=contract_time,
        )

        # Validate credentials early to produce a clearer 400 instead of a later generic 500
        if not (src.app_id and src.app_key):
            raise HTTPException(status_code=400, detail="Missing Adzuna credentials. Provide app_id & app_key (form fields) or set ADZUNA_APP_ID / ADZUNA_APP_KEY env vars.")

        t_fetch_start = time.perf_counter()
        try:
            jobs = src.fetch()
        except AdzunaAuthError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except AdzunaRateLimitError as e:
            raise HTTPException(status_code=429, detail=str(e))
        except AdzunaNetworkError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except AdzunaHTTPError as e:
            raise HTTPException(status_code=502, detail=f"{e.message} (status {e.status})")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Unexpected Adzuna error: {e}")

        jobs = normalize_ids(jobs, src.name)
        timings['fetch_sec'] = round(time.perf_counter() - t_fetch_start, 3)

        # Fallback provider if Adzuna returned zero jobs (optional toggle)
        fb_enabled = os.getenv('JOBMINER_FALLBACK_ENABLED','1').lower() in ('1','true','yes','on')
        if fb_enabled and len(jobs) == 0:
            try:
                remotive = RemotiveSource(what=title)
                fb_jobs = remotive.fetch()
                if fb_jobs:
                    jobs.extend(normalize_ids(fb_jobs, remotive.name))
            except Exception:
                pass

        # Optional client-side filtering for work_mode hints (best-effort)
        if work_mode and work_mode.lower() in ("remote", "hybrid", "onsite"):
            wm = work_mode.lower()
            jobs = [j for j in jobs if (j.work_mode or "").lower() == wm]

        # Apply a hard cap early if limit specified (pre-scoring) to reduce latency
        if limit is not None:
            try:
                lim = max(1, min(int(limit), 100))
            except Exception:
                lim = 50
        else:
            lim = 50
        if len(jobs) > lim:
            jobs = jobs[:lim]

        # Upsert into DB and run scoring using the detected resume profile
        db.upsert_jobs(jobs)

        # Seed skills file path; default project config
        seed_path = Path("scraper/config/seed_skills.txt")
        if not seed_path.exists():
            tokens = [t for t in re.split(r"[^A-Za-z0-9+.#-]+", title) if t]
            seed_path.write_text("\n".join(tokens), encoding="utf-8")

        # Scoring
        t_score_start = time.perf_counter()
        if jobs:
            score_all(db, tmp_resume_path, seed_path, write_summary=False, max_workers=1)
        timings['scoring_sec'] = round(time.perf_counter() - t_score_start, 3)

        # Export
        export_dir = TMP_DIR / uuid.uuid4().hex
        exporter = Exporter(db, export_dir, stream=True)
        t_export_start = time.perf_counter()
        artifacts = exporter.export_all() or {}
        full_csv = artifacts.get('full_csv')
        if not full_csv or not Path(full_csv).exists():
            if not jobs:
                out_rows = []
                data = b"title,company_name,location\n"
                token = uuid.uuid4().hex
                TOKENS[token] = { 'data': data, 'created': datetime.now(timezone.utc) }
                return JSONResponse({"token": token, "count": 0, "empty": True, "timings": timings})
            raise HTTPException(status_code=500, detail="Failed to build CSV after scoring")

        out_rows = []
        with open(full_csv, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                out_rows.append(row)
                if i + 1 >= lim:
                    break
        timings['export_sec'] = round(time.perf_counter() - t_export_start, 3)

        slim_cols = [
            'title','company_name','location','work_mode','employment_type','posted_at',
            'offered_salary_min','offered_salary_max','offered_salary_currency','salary_period','salary_is_predicted',
            'skill_score','skill_precision','skill_recall','skill_overlap_count','skill_core_size','semantic_score','score_total','matched_skills','apply_url','top_skills'
        ]
        if out_rows:
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=slim_cols)
            writer.writeheader()
            for r in out_rows:
                row = {k: r.get(k) for k in slim_cols}
                if not row.get('top_skills'):
                    ms = r.get('matched_skills') or ''
                    if ms:
                        parts = [p.strip() for p in ms.split(',') if p.strip()][:5]
                        if parts:
                            row['top_skills'] = ", ".join(parts)
                writer.writerow(row)
            data = buf.getvalue().encode('utf-8')
        else:
            data = b"title\n"
    finally:
        try:
            os.remove(tmp_resume_path)
        except Exception:
            pass

    token = uuid.uuid4().hex
    _prune_tokens()
    created = datetime.now(timezone.utc)
    TOKENS[token] = { 'data': data, 'created': created }
    # Write artifact to disk for persistence across reload
    try:
        file_path = TMP_DIR / f"{token}.csv"
        with open(file_path, 'wb') as fh:
            fh.write(data)
    except Exception:
        pass
    # Persist token metadata
    _prune_tokens()  # also saves state
    timings['total_sec'] = round(time.perf_counter() - t_total_start, 3)
    return JSONResponse({"token": token, "count": len(out_rows), "empty": len(out_rows)==0, "timings": timings})

@app.get("/api/download")
async def download(token: str, request: Request):
    _prune_tokens()
    entry = TOKENS.get(token)
    blob = entry['data'] if entry else None
    if not blob:
        # Attempt to read from disk (survives reload)
        file_path = TMP_DIR / f"{token}.csv"
        if file_path.exists():
            # Check TTL
            age = datetime.now(timezone.utc) - datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
            if age <= TOKEN_TTL:
                try:
                    blob = file_path.read_bytes()
                    # Rehydrate data into TOKENS (so future calls are in-memory)
                    if entry:
                        entry['data'] = blob
                    else:
                        TOKENS[token] = {'data': blob, 'created': datetime.now(timezone.utc)}
                except Exception:
                    blob = None
    if not blob:
        raise HTTPException(status_code=404, detail="Not found or expired")
    # Per-IP daily limit
    ip = request.client.host if request.client else 'unknown'
    if not _check_download_limit(ip):
        raise HTTPException(status_code=429, detail="Daily download limit reached (3)")
    filename = f"job_results_{token[:8]}.csv"
    return StreamingResponse(io.BytesIO(blob), media_type="text/csv", headers={
        "Content-Disposition": f"attachment; filename={filename}"
    })

@app.get("/health")
def health():
    _prune_tokens()
    return {"status":"ok","tokens_active": len(TOKENS), "rate_window": RATE_LIMIT_WINDOW, "rate_used": len(LAST_CALLS), "download_ips": len(DOWNLOAD_COUNTS)}

@app.get("/api/skill_gaps")
def skill_gaps(token: Optional[str] = None, limit: int = 10):
    """Return prioritized skill gaps (details JSON) for the most recent export.

    Since the async job pipeline currently does not persist a direct mapping from token -> export directory,
    we heuristically search recent TMP_DIR subdirectories for a skill_gaps_details.json file. If a token is
    provided we prefer a directory whose name shares prefix with the token (future improvement: persist mapping).
    """
    # Sanitize limit
    try:
        limit = max(1, min(int(limit), 50))
    except Exception:
        limit = 10
    candidates: List[Path] = []
    try:
        for p in TMP_DIR.iterdir():
            if p.is_dir():
                details = p / 'skill_gaps_details.json'
                if details.exists():
                    candidates.append(details)
    except Exception:
        pass
    if not candidates:
        return {'gaps': []}
    # Prefer token prefix match if provided
    selected = None
    if token:
        for d in candidates:
            if d.parent.name.startswith(token[:8]):  # loose heuristic
                selected = d; break
    # Fallback to most recent modified
    if not selected:
        selected = max(candidates, key=lambda p: p.stat().st_mtime)
    try:
        import json as _json
        data = _json.loads(selected.read_text(encoding='utf-8'))
        # Sort by priority_score desc if present
        # Skip achieved (do not recommend again)
        if sk in achieved:
            continue
        unmet = unresolved_prereqs(sk, achieved)
        if unmet:
            item['blocked_by'] = unmet
        adaptive.append(item)
    # Ranking adjustments:
    # 1. Unblocked before blocked
    # 2. Within those, priority_score desc (if present)
    # 3. Deprioritize in_progress slightly vs planned/untracked
    def rank_key(it):
        blocked = 1 if 'blocked_by' in it else 0
        prio = it.get('priority_score', 0) or 0
        status = it.get('progress_status')
        status_penalty = 0.1 if status == 'in_progress' else 0.0
        return (blocked, -(prio - status_penalty))
    adaptive.sort(key=rank_key)
    # Trim to limit
    adaptive = adaptive[:limit]
    return {'recommendations': adaptive, 'count': len(adaptive), 'dependencies_loaded': bool(deps)}

@app.get('/api/skill_progress')
def api_list_skill_progress(status: str | None = None):
    rows = list_progress(filter_status=status)
    return {'progress': rows, 'count': len(rows)}

@app.post('/api/skill_progress')
async def api_upsert_skill_progress(req: Request):
    try:
        payload = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail='Invalid JSON body')
    skill = (payload or {}).get('skill')
    status = (payload or {}).get('status')
    note = (payload or {}).get('note')
    if not skill or not status:
        raise HTTPException(status_code=400, detail='skill and status required')
    try:
        record = upsert_progress(skill, status, note=note)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    return {'progress': record}

@app.get('/api/skill_progress/metrics')
def api_skill_progress_metrics(weeks: int = 8):
    try:
        metrics = compute_velocity_metrics(weeks=weeks)
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to compute metrics: {e}')

@app.get('/api/job_details')
def api_job_details(limit: int = 50, db_path: str | None = None):
    """Return enriched per-job skill detail for recently processed jobs.

    This surfaces for each job:
      - job_id, title, company_name, score_total
      - top_matched: up to 5 highest-weight matched skills (from skills_extracted order)
      - semantic_added: skills inferred via semantic matching (skills_meta.semantic_added)
      - overlap_added: responsibility overlap-derived skills (skills_meta.overlap_added)

    We currently don't persist the scoring order separately; we rely on stored skills_extracted order.
    Future improvement: include per-skill weighting breakdown.
    """
    try:
        lim = max(1, min(int(limit), 200))
    except Exception:
        lim = 50
    db = JobDB(db_path) if db_path else JobDB()
    jobs = db.fetch_all()
    # Order by score_total desc if available
    jobs.sort(key=lambda j: (j.score_total is None, j.score_total or 0), reverse=True)
    out = []
    for j in jobs[:lim]:
        meta = j.skills_meta or {}
        sem_added = [s.get('skill') for s in (meta.get('semantic_added') or []) if s.get('skill')]
        overlap_added = [s.get('skill') for s in (meta.get('overlap_added') or []) if s.get('skill')]
        # Distinguish semantic-only (semantic_added minus any overlap_added duplicates)
        sem_only = [s for s in sem_added if s not in overlap_added]
        top_matched = (j.skills_extracted or [])[:5]
        out.append({
            'job_id': j.job_id,
            'title': j.title,
            'company_name': j.company_name,
            'score_total': j.score_total,
            'top_matched': top_matched,
            'semantic_only': sem_only,
            'overlap_added': overlap_added,
            'provenance': j.provenance or []
        })
    return {'jobs': out, 'count': len(out)}

@app.get('/api/metrics')
def api_metrics():
    """Return lightweight operational metrics for recent jobs & events."""
    with JOBS_LOCK:
        jobs_snapshot = list(JOBS.values())
    counts = { 'total': len(jobs_snapshot) }
    status_counts: Dict[str,int] = {}
    fetch_secs = []; score_secs = []; export_secs = []; total_secs = []
    for jr in jobs_snapshot:
        status_counts[jr.status] = status_counts.get(jr.status,0)+1
        t = jr.timings
        if 'fetch_sec' in t: fetch_secs.append(t['fetch_sec'])
        if 'scoring_sec' in t: score_secs.append(t['scoring_sec'])
        if 'export_sec' in t: export_secs.append(t['export_sec'])
        if 'total_sec' in t: total_secs.append(t['total_sec'])
    def avg(nums):
        return round(sum(nums)/len(nums),3) if nums else None
    with EVENTS_LOCK:
        events_tail = EVENTS[-25:]
    metrics = {
        'jobs': counts,
        'statuses': status_counts,
        'avg_fetch_sec': avg(fetch_secs),
        'avg_scoring_sec': avg(score_secs),
        'avg_export_sec': avg(export_secs),
        'avg_total_sec': avg(total_secs),
        'tokens_active': len(TOKENS),
        'download_ips': len(DOWNLOAD_COUNTS),
        'event_tail': events_tail,
    }
    return metrics

@app.get('/api/health/summary')
def api_health_summary(limit: int = 50):
    """Aggregate recent run snapshots and surface simple anomaly flags.

    Anomalies flagged:
      - fetch_sec_spike: latest fetch_sec > 1.5 * median previous (where previous >=5 samples)
      - zero_jobs_streak: >=3 consecutive completed runs with count == 0
      - error_rate_high: error rate over window > 0.3 with >=5 samples
    """
    try:
        limit = max(5, min(int(limit), 500))
    except Exception:
        limit = 50
    snap_file = TMP_DIR / 'snapshots' / 'runs.jsonl'
    runs = []
    if snap_file.exists():
        try:
            with open(snap_file, 'r', encoding='utf-8') as fh:
                for line in fh.readlines()[-limit:]:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        runs.append(_json.loads(line))
                    except Exception:
                        continue
        except Exception:
            pass
    total = len(runs)
    if not runs:
        return {'runs': 0, 'anomalies': [], 'averages': {}, 'latest': None}
    # Compute averages for timing keys
    fetch_vals = [r['timings'].get('fetch_sec') for r in runs if r.get('timings',{}).get('fetch_sec') is not None]
    score_vals = [r['timings'].get('scoring_sec') for r in runs if r.get('timings',{}).get('scoring_sec') is not None]
    export_vals = [r['timings'].get('export_sec') for r in runs if r.get('timings',{}).get('export_sec') is not None]
    total_vals = [r['timings'].get('total_sec') for r in runs if r.get('timings',{}).get('total_sec') is not None]
    def _avg(v): return round(sum(v)/len(v),3) if v else None
    def _median(v):
        if not v: return None
        sv = sorted(v); n=len(sv); m=n//2
        return sv[m] if n%2==1 else (sv[m-1]+sv[m])/2
    anomalies = []
    # fetch_sec spike
    if len(fetch_vals) >= 6:
        latest_fetch = fetch_vals[-1]
        prev_med = _median(fetch_vals[:-1])
        if prev_med and latest_fetch and latest_fetch > 1.5 * prev_med:
            anomalies.append({'type':'fetch_sec_spike','latest': latest_fetch,'prev_median': round(prev_med,3)})
    # zero jobs streak
    streak = 0
    for r in reversed(runs):
        if r.get('status') == 'done' and (r.get('count') or 0) == 0:
            streak += 1
        elif r.get('status') == 'done':
            break
    if streak >= 3:
        anomalies.append({'type':'zero_jobs_streak','length': streak})
    # error rate
    errors = sum(1 for r in runs if r.get('status') == 'error')
    if total >= 5:
        err_rate = errors / total
        if err_rate > 0.3:
            anomalies.append({'type':'error_rate_high','error_rate': round(err_rate,3),'window': total})
    return {
        'runs': total,
        'averages': {
            'fetch_sec': _avg(fetch_vals),
            'scoring_sec': _avg(score_vals),
            'export_sec': _avg(export_vals),
            'total_sec': _avg(total_vals),
        },
        'latest': runs[-1],
        'anomalies': anomalies,
    }

@app.get("/api/debug/tokens")
def debug_tokens():
    """Lightweight debug endpoint (DO NOT expose publicly in production).
    Shows current token metadata and presence of artifact files to help diagnose 404 issues."""
    now = datetime.now(timezone.utc)
    items = []
    for k,v in TOKENS.items():
        created = v.get('created')
        age_s = (now - created).total_seconds() if created else None
        fpath = TMP_DIR / f"{k}.csv"
        items.append({
            'token': k,
            'age_sec': round(age_s,2) if age_s is not None else None,
            'in_memory': v.get('data') is not None,
            'file_exists': fpath.exists(),
            'file_size': fpath.stat().st_size if fpath.exists() else None,
        })
    # Also list stray files
    stray_files = []
    try:
        for p in TMP_DIR.glob('*.csv'):
            t = p.stem
            if t not in TOKENS:
                stray_files.append({'file': p.name, 'size': p.stat().st_size})
    except Exception:
        pass
    return {'tokens': items, 'stray_files': stray_files, 'tmp_dir': str(TMP_DIR)}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port)
