from pathlib import Path
import tempfile
import os
import time
from datetime import datetime, timezone

import pandas as pd

from scraper.jobminer.db import JobDB
from scraper.jobminer.models import JobPosting
from scraper.jobminer.exporter import Exporter


def make_job(job_id: str, status: str = 'new', title: str = 'Engineer') -> JobPosting:
    return JobPosting(
        job_id=job_id,
        title=title,
        company_name='Acme',
        location='Seattle, WA, United States',
        work_mode='remote',
        collected_at=datetime.now(timezone.utc),
        description_raw='desc',
        description_clean='Responsible for data engineering',
        employment_type='Full-time',
        seniority_level='Mid-Senior',
        skills_extracted=['Python'],
        recruiter_profiles=[],
        benefits=[],
        status=status,
        score_total=0.75,
    )


def test_exporter_excludes_duplicates():
    # Use explicit close + file removal to avoid Windows temp file lock
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / 'db.sqlite'
        db = JobDB(db_path)
        try:
            j1 = make_job('1', status='new')
            j2 = make_job('2', status='duplicate')
            db.upsert_jobs([j1, j2])
            export_dir = Path(td) / 'exports'
            exp = Exporter(db, export_dir)
            paths = exp.export_all()
            assert paths is not None
            df = pd.read_csv(paths.get('full_csv', paths['full']), dtype={'job_id': str})
            # Ensure job_id column loaded as object/string dtype
            assert df['job_id'].dtype == object
            job_ids = set(df['job_id'].astype(str))
            assert '2' not in job_ids
            assert '1' in job_ids
        finally:
            db.close()
            for _ in range(5):
                try:
                    if db_path.exists():
                        os.remove(db_path)
                    break
                except PermissionError:
                    time.sleep(0.2)
