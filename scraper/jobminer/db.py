"""SQLite persistence layer for JobMiner.

This file was reconstructed after corruption. It provides a persistent connection
`JobDB` class used by exporters and scoring code. It also persists a `provenance`
column (JSON array) capturing all contributing sources for a merged job posting.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, List

from .models import JobPosting
from .settings import SCHEMA_VERSION

DB_FILE = Path(__file__).resolve().parent.parent / "data" / "db.sqlite"

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
    skills_meta TEXT,
    provenance TEXT
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
    """Lightweight wrapper around a persistent sqlite3 connection.

    ResourceWarnings were previously emitted due to unclosed connections when
    many short-lived JobDB instances were created. A single persistent
    connection per instance plus deterministic close() fixes that.
    """

    def __init__(self, db_path: Path | str = DB_FILE):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._closed = False
        self._init_schema()

    # ------------------------- schema & migrations -------------------------
    def _init_schema(self):
        conn = self._conn
        conn.execute(SCHEMA_SQL)
        conn.execute(META_TABLE_SQL)
        # status history (executescript handles both statements)
        try:
            conn.executescript(STATUS_HISTORY_SQL)
        except Exception:
            # fallback if executescript partially fails
            for stmt in STATUS_HISTORY_SQL.split(";"):
                s = stmt.strip()
                if s:
                    try:
                        conn.execute(s)
                    except Exception:
                        pass

        # Read existing schema version
        try:
            cur = conn.execute("SELECT value FROM meta WHERE key='schema_version'")
            row = cur.fetchone()
            current_version = int(row[0]) if row else None
        except Exception:
            current_version = None

        # Idempotent column additions (future proofing)
        try:
            cur = conn.execute("PRAGMA table_info(jobs)")
            cols = [r[1] for r in cur.fetchall()]
            def add(col: str, ddl_tail: str):
                if col not in cols:
                    try:
                        conn.execute(f"ALTER TABLE jobs ADD COLUMN {ddl_tail}")
                    except Exception:
                        pass
            add("page_title", "page_title TEXT")
            add("skills_meta", "skills_meta TEXT")
            add("provenance", "provenance TEXT")
            add("company_name_normalized", "company_name_normalized TEXT")
            add("location_normalized", "location_normalized TEXT")
            add("location_meta", "location_meta TEXT")
            add("company_map_key", "company_map_key TEXT")
            add("normalization_version", "normalization_version TEXT")
            add("enrichment_run_at", "enrichment_run_at TEXT")
            add("geocode_lat", "geocode_lat REAL")
            add("geocode_lon", "geocode_lon REAL")
            try:
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_jobs_norm_keys ON jobs(company_name_normalized, location_normalized, title)"
                )
            except Exception:
                pass
        except Exception:
            pass

        # Update schema version marker
        try:
            if current_version != SCHEMA_VERSION:
                conn.execute(
                    "INSERT INTO meta(key,value) VALUES('schema_version', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(SCHEMA_VERSION),),
                )
        except Exception:
            pass
        conn.commit()

    # ----------------------------- lifecycle ------------------------------
    def close(self):
        if not self._closed:
            try:
                self._conn.commit()
                self._conn.close()
            except Exception:
                pass
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def __del__(self):  # safety net
        try:
            self.close()
        except Exception:
            pass

    # ------------------------------ operations ----------------------------
    def upsert_jobs(self, jobs: Iterable[JobPosting]):
        rows = [self._job_to_row(j) for j in jobs]
        conn = self._conn
        conn.executemany(
            """
            INSERT INTO jobs (
                job_id, title, company_name, page_title, company_linkedin_id, location, work_mode, company_name_normalized, location_normalized, location_meta, company_map_key, normalization_version, enrichment_run_at, geocode_lat, geocode_lon, posted_at, collected_at,
                employment_type, seniority_level, skills_extracted, description_raw, description_clean,
                apply_method, apply_url, recruiter_profiles, offered_salary_min, offered_salary_max,
                offered_salary_currency, benefits, score_total, score_breakdown, status, skills_meta, provenance
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                skills_meta=excluded.skills_meta,
                provenance=excluded.provenance
        """,
            rows,
        )
        conn.commit()

    def fetch_all(self) -> List[JobPosting]:
        cur = self._conn.execute("SELECT * FROM jobs")
        cols = [c[0] for c in cur.description]
        out: List[JobPosting] = []
        for r in cur.fetchall():
            data = dict(zip(cols, r))
            out.append(self._row_to_job(data))
        return out

    def fetch_by_id(self, job_id: str) -> JobPosting | None:
        cur = self._conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        data = dict(zip(cols, row))
        return self._row_to_job(data)

    def update_status(self, job_id: str, status: str):
        import datetime as dt
        cur = self._conn.execute("SELECT status FROM jobs WHERE job_id=?", (job_id,))
        row = cur.fetchone()
        prev = row[0] if row else None
        if prev == status:
            return
        self._conn.execute("UPDATE jobs SET status=? WHERE job_id=?", (status, job_id))
        self._conn.execute(
            "INSERT INTO status_history(job_id, from_status, to_status, changed_at) VALUES (?,?,?,?)",
            (job_id, prev, status, dt.datetime.utcnow().isoformat() + "Z"),
        )
        self._conn.commit()

    def fetch_history(self, job_id: str, limit: int = 20):
        cur = self._conn.execute(
            "SELECT from_status, to_status, changed_at FROM status_history WHERE job_id=? ORDER BY id DESC LIMIT ?",
            (job_id, limit),
        )
        return [dict(from_status=r[0], to_status=r[1], changed_at=r[2]) for r in cur.fetchall()]

    def funnel_metrics(self):
        cur = self._conn.execute("SELECT COUNT(*) FROM jobs")
        total = cur.fetchone()[0]
        def count_stage(stage: str):
            return self._conn.execute(
                "SELECT COUNT(DISTINCT job_id) FROM status_history WHERE to_status=?",
                (stage,),
            ).fetchone()[0]
        reviewed = count_stage("reviewed")
        shortlisted = count_stage("shortlisted")
        applied = count_stage("applied")
        def ratio(a, b):
            return 0.0 if b == 0 else round(a / b, 3)
        return {
            "total_jobs": total,
            "reviewed": reviewed,
            "shortlisted": shortlisted,
            "applied": applied,
            "review_rate": ratio(reviewed, total),
            "shortlist_rate": ratio(shortlisted, reviewed),
            "apply_rate": ratio(applied, shortlisted),
        }

    def update_scores(self, job: JobPosting):
        self._conn.execute(
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
        self._conn.commit()

    # ----------------------------- row helpers ----------------------------
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
            json.dumps(job.provenance) if getattr(job, "provenance", None) else None,
        )

    def _row_to_job(self, row: dict) -> JobPosting:
        import datetime as dt
        return JobPosting(
            job_id=row["job_id"],
            title=row["title"],
            company_name=row["company_name"],
            page_title=row.get("page_title"),
            company_linkedin_id=row.get("company_linkedin_id"),
            location=row["location"],
            work_mode=row["work_mode"],
            company_name_normalized=row.get("company_name_normalized"),
            location_normalized=row.get("location_normalized"),
            location_meta=json.loads(row["location_meta"]) if row.get("location_meta") else None,
            company_map_key=row.get("company_map_key"),
            normalization_version=row.get("normalization_version"),
            enrichment_run_at=dt.datetime.fromisoformat(row["enrichment_run_at"]) if row.get("enrichment_run_at") else None,
            geocode_lat=row.get("geocode_lat"),
            geocode_lon=row.get("geocode_lon"),
            posted_at=dt.date.fromisoformat(row["posted_at"]) if row["posted_at"] else None,
            collected_at=dt.datetime.fromisoformat(row["collected_at"]) if row["collected_at"] else None,
            employment_type=row["employment_type"],
            seniority_level=row["seniority_level"],
            skills_extracted=json.loads(row["skills_extracted"]) if row["skills_extracted"] else [],
            description_raw=row["description_raw"],
            description_clean=row["description_clean"],
            apply_method=row["apply_method"],
            apply_url=row["apply_url"],
            recruiter_profiles=json.loads(row["recruiter_profiles"]) if row["recruiter_profiles"] else [],
            offered_salary_min=row["offered_salary_min"],
            offered_salary_max=row["offered_salary_max"],
            offered_salary_currency=row["offered_salary_currency"],
            benefits=json.loads(row["benefits"]) if row["benefits"] else [],
            score_total=row["score_total"],
            score_breakdown=json.loads(row["score_breakdown"]) if row["score_breakdown"] else None,
            status=row["status"],
            skills_meta=json.loads(row["skills_meta"]) if row.get("skills_meta") else None,
            provenance=json.loads(row["provenance"]) if row.get("provenance") else [],
        )

