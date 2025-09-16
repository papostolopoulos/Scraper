from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Iterable, List
from .models import JobPosting
from .settings import SCHEMA_VERSION
import json

DB_FILE = Path(__file__).resolve().parent.parent / 'data' / 'db.sqlite'

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    title TEXT,
    company_name TEXT,
    page_title TEXT,
    company_linkedin_id TEXT,
    location TEXT,
    work_mode TEXT,
    company_name_normalized TEXT,
    location_normalized TEXT,
    location_meta TEXT,
    company_map_key TEXT,
    normalization_version TEXT,
    enrichment_run_at TEXT,
    geocode_lat REAL,
    geocode_lon REAL,
    posted_at TEXT,
    collected_at TEXT,
    employment_type TEXT,
    seniority_level TEXT,
    skills_extracted TEXT,
    description_raw TEXT,
    description_clean TEXT,
    apply_method TEXT,
    apply_url TEXT,
    recruiter_profiles TEXT,
    offered_salary_min REAL,
    offered_salary_max REAL,
    offered_salary_currency TEXT,
    benefits TEXT,
    score_total REAL,
    score_breakdown TEXT,
    status TEXT,
    skills_meta TEXT
);
"""

STATUS_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(job_id)
);
CREATE INDEX IF NOT EXISTS idx_status_history_job ON status_history(job_id);
"""

META_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

class JobDB:
    def __init__(self, db_path: Path = DB_FILE):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(SCHEMA_SQL)
            conn.execute(META_TABLE_SQL)
            conn.execute(STATUS_HISTORY_SQL)
            # schema version check
            try:
                cur = conn.execute("SELECT value FROM meta WHERE key='schema_version'")
                row = cur.fetchone()
                current_version = int(row[0]) if row else None
            except Exception:
                current_version = None
            # Lightweight migration: add page_title if missing
            try:
                cur = conn.execute("PRAGMA table_info(jobs)")
                cols = [r[1] for r in cur.fetchall()]
                if 'page_title' not in cols:
                    conn.execute("ALTER TABLE jobs ADD COLUMN page_title TEXT")
                if 'skills_meta' not in cols:
                    conn.execute("ALTER TABLE jobs ADD COLUMN skills_meta TEXT")
                if 'company_name_normalized' not in cols:
                    conn.execute("ALTER TABLE jobs ADD COLUMN company_name_normalized TEXT")
                if 'location_normalized' not in cols:
                    conn.execute("ALTER TABLE jobs ADD COLUMN location_normalized TEXT")
                if 'location_meta' not in cols:
                    conn.execute("ALTER TABLE jobs ADD COLUMN location_meta TEXT")
                if 'company_map_key' not in cols:
                    conn.execute("ALTER TABLE jobs ADD COLUMN company_map_key TEXT")
                if 'normalization_version' not in cols:
                    conn.execute("ALTER TABLE jobs ADD COLUMN normalization_version TEXT")
                if 'enrichment_run_at' not in cols:
                    conn.execute("ALTER TABLE jobs ADD COLUMN enrichment_run_at TEXT")
                if 'geocode_lat' not in cols:
                    conn.execute("ALTER TABLE jobs ADD COLUMN geocode_lat REAL")
                if 'geocode_lon' not in cols:
                    conn.execute("ALTER TABLE jobs ADD COLUMN geocode_lon REAL")
                # Physical removal of obsolete columns if they exist (offered_salary_period, offered_salary_raw)
                # SQLite cannot DROP COLUMN before 3.35 easily; recreate table if needed.
                obsolete = [c for c in ['offered_salary_period','offered_salary_raw'] if c in cols]
                if obsolete:
                    # Recreate without obsolete columns
                    conn.execute('BEGIN')
                    try:
                        conn.execute("ALTER TABLE jobs RENAME TO jobs_old")
                        conn.execute(SCHEMA_SQL)  # new schema w/out obsolete
                        # Map columns that still exist
                        new_cols = [
                            'job_id','title','company_name','page_title','company_linkedin_id','location','work_mode','company_name_normalized','location_normalized','location_meta','company_map_key','normalization_version','enrichment_run_at','geocode_lat','geocode_lon','posted_at','collected_at',
                            'employment_type','seniority_level','skills_extracted','description_raw','description_clean','apply_method','apply_url','recruiter_profiles',
                            'offered_salary_min','offered_salary_max','offered_salary_currency','benefits','score_total','score_breakdown','status','skills_meta'
                        ]
                        select_cols = ','.join(new_cols)
                        conn.execute(f"INSERT INTO jobs ({select_cols}) SELECT {select_cols} FROM jobs_old")
                        conn.execute("DROP TABLE jobs_old")
                        conn.execute('COMMIT')
                    except Exception:
                        conn.execute('ROLLBACK')
                # Create helpful index for dedupe / queries (ignore failures)
                try:
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_norm_keys ON jobs(company_name_normalized, location_normalized, title)")
                except Exception:
                    pass
            except Exception:
                pass
            # Update schema version if changed
            try:
                if current_version != SCHEMA_VERSION:
                    conn.execute("INSERT INTO meta(key,value) VALUES('schema_version', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(SCHEMA_VERSION),))
            except Exception:
                pass
        # No persistent connection kept; placeholder attribute for API symmetry
        self._closed = False

    def close(self):  # for explicit lifecycle control in tests (Windows file locks)
        self._closed = True
        # no persistent connection to close; method retained for API symmetry

    # Context manager helpers for use in tests to reduce Windows file lock timing issues
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def upsert_jobs(self, jobs: Iterable[JobPosting]):
        rows = [self._job_to_row(j) for j in jobs]
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany("""
                INSERT INTO jobs (
                    job_id, title, company_name, page_title, company_linkedin_id, location, work_mode, company_name_normalized, location_normalized, location_meta, company_map_key, normalization_version, enrichment_run_at, geocode_lat, geocode_lon, posted_at, collected_at,
                    employment_type, seniority_level, skills_extracted, description_raw, description_clean,
                    apply_method, apply_url, recruiter_profiles, offered_salary_min, offered_salary_max,
                    offered_salary_currency, benefits, score_total, score_breakdown, status, skills_meta
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(job_id) DO UPDATE SET
                    title=excluded.title,
                    company_name=excluded.company_name,
                    page_title=excluded.page_title,
                    company_linkedin_id=excluded.company_linkedin_id,
                    location=excluded.location,
                    work_mode=excluded.work_mode,
                    company_name_normalized=excluded.company_name_normalized,
                    location_normalized=excluded.location_normalized,
                    location_meta=excluded.location_meta,
                    company_map_key=excluded.company_map_key,
                    normalization_version=excluded.normalization_version,
                    enrichment_run_at=excluded.enrichment_run_at,
                    geocode_lat=excluded.geocode_lat,
                    geocode_lon=excluded.geocode_lon,
                    posted_at=excluded.posted_at,
                    collected_at=excluded.collected_at,
                    employment_type=excluded.employment_type,
                    seniority_level=excluded.seniority_level,
                    skills_extracted=excluded.skills_extracted,
                    description_raw=excluded.description_raw,
                    description_clean=excluded.description_clean,
                    apply_method=excluded.apply_method,
                    apply_url=excluded.apply_url,
                    recruiter_profiles=excluded.recruiter_profiles,
                    offered_salary_min=excluded.offered_salary_min,
                    offered_salary_max=excluded.offered_salary_max,
                    offered_salary_currency=excluded.offered_salary_currency,
                    benefits=excluded.benefits,
                    score_total=excluded.score_total,
                    score_breakdown=excluded.score_breakdown,
                    status=excluded.status,
                    skills_meta=excluded.skills_meta
            """, rows)

    def fetch_all(self) -> List[JobPosting]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT * FROM jobs")
            cols = [c[0] for c in cur.description]
            out = []
            for r in cur.fetchall():
                data = dict(zip(cols, r))
                out.append(self._row_to_job(data))
            return out

    def fetch_by_id(self, job_id: str) -> JobPosting | None:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,))
            row = cur.fetchone()
            if not row:
                return None
            cols = [c[0] for c in cur.description]
            data = dict(zip(cols, row))
            return self._row_to_job(data)

    def update_status(self, job_id: str, status: str):
        import datetime as dt
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT status FROM jobs WHERE job_id=?", (job_id,))
            row = cur.fetchone()
            prev = row[0] if row else None
            if prev == status:
                return  # no-op
            conn.execute("UPDATE jobs SET status=? WHERE job_id=?", (status, job_id))
            conn.execute(
                "INSERT INTO status_history(job_id, from_status, to_status, changed_at) VALUES (?,?,?,?)",
                (job_id, prev, status, dt.datetime.utcnow().isoformat()+"Z"),
            )

    def fetch_history(self, job_id: str, limit: int = 20):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT from_status, to_status, changed_at FROM status_history WHERE job_id=? ORDER BY id DESC LIMIT ?",
                (job_id, limit),
            )
            return [dict(from_status=r[0], to_status=r[1], changed_at=r[2]) for r in cur.fetchall()]

    def funnel_metrics(self):
        """Return basic pipeline funnel counts & conversion ratios.

        stages order: new -> reviewed -> shortlisted -> applied
        Counts: total jobs currently ever seen, and how many reached each stage at least once.
        Ratios: reviewed/new, shortlisted/reviewed, applied/shortlisted (float rounded 3dp).
        """
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT COUNT(*) FROM jobs")
            total = cur.fetchone()[0]
            # Using history to see if a job ever transitioned INTO a stage (to_status)
            def count_stage(stage: str):
                c = conn.execute("SELECT COUNT(DISTINCT job_id) FROM status_history WHERE to_status=?", (stage,)).fetchone()[0]
                return c
            reviewed = count_stage('reviewed')
            shortlisted = count_stage('shortlisted')
            applied = count_stage('applied')
            def ratio(a, b):
                if b == 0:
                    return 0.0
                return round(a / b, 3)
            return {
                'total_jobs': total,
                'reviewed': reviewed,
                'shortlisted': shortlisted,
                'applied': applied,
                'review_rate': ratio(reviewed, total),
                'shortlist_rate': ratio(shortlisted, reviewed),
                'apply_rate': ratio(applied, shortlisted),
            }

    def update_scores(self, job: JobPosting):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE jobs SET score_total=?, score_breakdown=?, status=?, skills_extracted=?, benefits=?, skills_meta=? WHERE job_id=?",
                (
                    job.score_total,
                    json.dumps(job.score_breakdown) if job.score_breakdown else None,
                    job.status,
                    json.dumps(job.skills_extracted) if job.skills_extracted else None,
                    json.dumps(job.benefits) if job.benefits else None,
                    json.dumps(job.skills_meta) if job.skills_meta else None,
                    job.job_id,
                ),
            )

    def _job_to_row(self, job: JobPosting):
        return (
            job.job_id,
            job.title,
            job.company_name,
            job.page_title,
            job.company_linkedin_id,
            job.location,
            job.work_mode,
            job.company_name_normalized,
            job.location_normalized,
            json.dumps(job.location_meta) if job.location_meta else None,
            job.company_map_key,
            job.normalization_version,
            job.enrichment_run_at.isoformat() if job.enrichment_run_at else None,
            job.geocode_lat,
            job.geocode_lon,
            job.posted_at.isoformat() if job.posted_at else None,
            job.collected_at.isoformat(),
            job.employment_type,
            job.seniority_level,
            json.dumps(job.skills_extracted),
            job.description_raw,
            job.description_clean,
            job.apply_method,
            job.apply_url,
            json.dumps(job.recruiter_profiles),
            job.offered_salary_min,
            job.offered_salary_max,
            job.offered_salary_currency,
            json.dumps(job.benefits),
            job.score_total,
            json.dumps(job.score_breakdown) if job.score_breakdown else None,
            job.status,
            json.dumps(job.skills_meta) if job.skills_meta else None,
        )

    def _row_to_job(self, row: dict) -> JobPosting:
        import datetime as dt
        return JobPosting(
            job_id=row['job_id'],
            title=row['title'],
            company_name=row['company_name'],
            page_title=row.get('page_title'),
            company_linkedin_id=row.get('company_linkedin_id'),
            location=row['location'],
            work_mode=row['work_mode'],
            company_name_normalized=row.get('company_name_normalized'),
            location_normalized=row.get('location_normalized'),
            location_meta=json.loads(row['location_meta']) if row.get('location_meta') else None,
            company_map_key=row.get('company_map_key'),
            normalization_version=row.get('normalization_version'),
            enrichment_run_at=dt.datetime.fromisoformat(row['enrichment_run_at']) if row.get('enrichment_run_at') else None,
            geocode_lat=row.get('geocode_lat'),
            geocode_lon=row.get('geocode_lon'),
            posted_at=dt.date.fromisoformat(row['posted_at']) if row['posted_at'] else None,
            collected_at=dt.datetime.fromisoformat(row['collected_at']) if row['collected_at'] else None,
            employment_type=row['employment_type'],
            seniority_level=row['seniority_level'],
            skills_extracted=json.loads(row['skills_extracted']) if row['skills_extracted'] else [],
            description_raw=row['description_raw'],
            description_clean=row['description_clean'],
            apply_method=row['apply_method'],
            apply_url=row['apply_url'],
            recruiter_profiles=json.loads(row['recruiter_profiles']) if row['recruiter_profiles'] else [],
            offered_salary_min=row['offered_salary_min'],
            offered_salary_max=row['offered_salary_max'],
            offered_salary_currency=row['offered_salary_currency'],
            benefits=json.loads(row['benefits']) if row['benefits'] else [],
            score_total=row['score_total'],
            score_breakdown=json.loads(row['score_breakdown']) if row['score_breakdown'] else None,
            status=row['status'],
            skills_meta=json.loads(row['skills_meta']) if row.get('skills_meta') else None,
        )
