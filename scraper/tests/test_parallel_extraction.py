from pathlib import Path
import os
from scraper.jobminer.db import JobDB
from scraper.jobminer.models import JobPosting
from scraper.jobminer.pipeline import score_all
import datetime as dt


def make_job(i):
    return JobPosting(
        job_id=str(i),
        title='Engineer',
        company_name='Acme',
        location='Remote',
        work_mode='remote',
        collected_at=dt.datetime.utcnow(),
        description_raw='We use Python and SQL to build data pipelines',
        description_clean='We use Python and SQL to build data pipelines',
        employment_type='Full-time',
        seniority_level='Mid',
        skills_extracted=[],
        recruiter_profiles=[],
        benefits=[],
        status='new'
    )


def test_parallel_vs_serial_equivalence(tmp_path, monkeypatch):
    db_path = tmp_path/'db.sqlite'
    db = JobDB(db_path)
    jobs = [make_job(i) for i in range(6)]
    db.upsert_jobs(jobs)
    seed = tmp_path/'skills.txt'
    seed.write_text('Python\nSQL\nPipelines\n', encoding='utf-8')
    resume = tmp_path/'resume.pdf'
    resume.write_bytes(b"%PDF-1.3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF")
    # Serial
    score_all(db, resume, seed, max_workers=1)
    serial_jobs = {j.job_id: (j.score_total, tuple(j.skills_extracted)) for j in db.fetch_all()}
    # Reset skills & scores
    all_jobs = db.fetch_all()
    for j in all_jobs:
        j.skills_extracted = []
        j.score_total = None
    db.upsert_jobs(all_jobs)
    # Parallel
    score_all(db, resume, seed, max_workers=4)
    parallel_jobs = {j.job_id: (j.score_total, tuple(j.skills_extracted)) for j in db.fetch_all()}
    assert serial_jobs == parallel_jobs
