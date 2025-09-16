import sqlite3, json
from pathlib import Path
from scraper.jobminer.db import JobDB
from scraper.jobminer.settings import SCHEMA_VERSION

OLD_SCHEMA = """
CREATE TABLE jobs (
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
    status TEXT
);
"""

def test_schema_version_migration(tmp_path):
    db_path = tmp_path / 'legacy.sqlite'
    with sqlite3.connect(db_path) as conn:
        conn.executescript(OLD_SCHEMA)
    # Instantiate modern DB (should add missing columns + meta table/version)
    JobDB(db_path)
    with sqlite3.connect(db_path) as conn:
        # verify meta table & version
        cur = conn.execute("SELECT value FROM meta WHERE key='schema_version'")
        row = cur.fetchone()
        assert row is not None
        assert int(row[0]) == SCHEMA_VERSION
        # verify new column exists
        cols = [r[1] for r in conn.execute('PRAGMA table_info(jobs)')]
        assert 'skills_meta' in cols
