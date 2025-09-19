from __future__ import annotations
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
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

app = FastAPI(title="Job Miner Web MVP")

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

TMP_DIR = Path("scraper/web/tmp")
TMP_DIR.mkdir(parents=True, exist_ok=True)

# In-memory registry mapping token -> {data: bytes, created: datetime}
TOKENS: dict[str, dict] = {}

# Simple in-memory rate limiting (global prepare endpoint)
LAST_CALLS: list[datetime] = []
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 12     # max prepare calls per window

# Per-IP download daily counters
DOWNLOAD_COUNTS: dict[str, dict] = {}
MAX_DOWNLOADS_PER_DAY = 3

TOKEN_TTL = timedelta(minutes=10)

def _prune_tokens():
    now = datetime.now(timezone.utc)
    expired = [k for k,v in TOKENS.items() if (now - v['created']) > TOKEN_TTL]
    for k in expired:
        TOKENS.pop(k, None)

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

        src = AdzunaSource(
            name="adzuna",
            app_id=app_id or os.getenv("ADZUNA_APP_ID"),
            app_key=app_key or os.getenv("ADZUNA_APP_KEY"),
            country=(country or "us").lower(),
            what=title,
            where=location,
            distance=int(distance),
            max_pages=3,
            results_per_page=50,
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
        # Trim job list before scoring if oversized (keep ordering as fetched)
        if len(jobs) > lim:
            jobs = jobs[:lim]

        # Upsert into DB and run scoring using the detected resume profile
        db.upsert_jobs(jobs)

        # Seed skills file path; default project config
        seed_path = Path("scraper/config/seed_skills.txt")
        if not seed_path.exists():
            # fallback minimal seeds derived from title tokens
            tokens = [t for t in re.split(r"[^A-Za-z0-9+.#-]+", title) if t]
            seed_path.write_text("\n".join(tokens), encoding="utf-8")

        # Score all with 1 worker to keep latency predictable for web
        t_score_start = time.perf_counter()
        if jobs:
            score_all(db, tmp_resume_path, seed_path, write_summary=False, max_workers=1)
        timings['scoring_sec'] = round(time.perf_counter() - t_score_start, 3)

        # Export streaming CSVs to a temp dir and return the full.csv content (capped later by UI)
        export_dir = TMP_DIR / uuid.uuid4().hex
        exporter = Exporter(db, export_dir, stream=True)
    t_export_start = time.perf_counter()
    artifacts = exporter.export_all() or {}
        full_csv = artifacts.get('full_csv')
        if not full_csv or not Path(full_csv).exists():
            if not jobs:
                # Return empty CSV gracefully
                out_rows = []
                data = b"title,company_name,location\n"
                token = uuid.uuid4().hex
                TOKENS[token] = { 'data': data, 'created': datetime.now(timezone.utc) }
                return JSONResponse({"token": token, "count": 0, "empty": True})
            raise HTTPException(status_code=500, detail="Failed to build CSV after scoring")
        # Load and cap to requested limit (already truncated pre-scoring, but safeguard in case export has more)
        out_rows = []
        with open(full_csv, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                out_rows.append(row)
                if i + 1 >= lim:
                    break
        timings['export_sec'] = round(time.perf_counter() - t_export_start, 3)
        # Re-write a compact CSV with enriched columns for download (component scores, salaries, top skills)
        slim_cols = [
            'title','company_name','location','work_mode','employment_type','posted_at',
            'offered_salary_min','offered_salary_max','offered_salary_currency','salary_period','salary_is_predicted',
            'offered_salary_min_usd','offered_salary_max_usd','skill_score','semantic_score','score_total','matched_skills','apply_url','top_skills'
        ]
        if out_rows:
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=slim_cols)
            writer.writeheader()
            for r in out_rows:
                row = {k: r.get(k) for k in slim_cols}
                # Derive top_skills: use first 5 matched_skills tokens
                if not row.get('top_skills'):
                    ms = r.get('matched_skills') or ''
                    if ms:
                        parts = [p.strip() for p in ms.split(',') if p.strip()][:5]
                        if parts:
                            row['top_skills'] = ", ".join(parts)
                writer.writerow(row)
            data = buf.getvalue().encode('utf-8')
        else:
            data = b"title\n"  # empty placeholder
    finally:
        try:
            os.remove(tmp_resume_path)
        except Exception:
            pass

    token = uuid.uuid4().hex
    _prune_tokens()
    TOKENS[token] = { 'data': data, 'created': datetime.now(timezone.utc) }
    timings['total_sec'] = round(time.perf_counter() - t_total_start, 3)
    return JSONResponse({"token": token, "count": len(out_rows), "empty": len(out_rows)==0, "timings": timings})

@app.get("/api/download")
async def download(token: str, request: Request):
    _prune_tokens()
    entry = TOKENS.get(token)
    blob = entry['data'] if entry else None
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

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port)
