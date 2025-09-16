from pathlib import Path
from datetime import datetime, timezone
import json
from scraper.jobminer.db import JobDB
from scraper.jobminer.models import JobPosting
import subprocess, sys


def test_summary_json_contains_distribution_and_timing():
    # Use real pipeline script in enrich-only mode
    base = Path('scraper')
    db = JobDB()  # default path
    # Insert a job with a score_total so distribution has data
    job = JobPosting(
        job_id='dist1', title='Data Engineer', company_name='Acme', location='Seattle, WA, United States',
        work_mode='remote', collected_at=datetime.now(timezone.utc), description_raw='d', description_clean='Build pipelines',
        employment_type='Full-time', seniority_level='Mid-Senior', skills_extracted=['Python'], recruiter_profiles=[], benefits=[], status='new', score_total=0.9
    )
    db.upsert_jobs([job])
    summary_name = 'test_summary.json'
    # Run pipeline enrich-only (won't alter existing score)
    cmd = [sys.executable, 'scraper/scripts/run_pipeline.py', '--enrich-only', '--no-export', '--summary-json', summary_name]
    subprocess.run(cmd, check=True)
    summary_file = Path('scraper/data/exports') / summary_name
    assert summary_file.exists()
    data = json.loads(summary_file.read_text(encoding='utf-8'))
    assert 'score_distribution' in data
    assert 'timing' in data
    assert data['score_distribution']['count'] >= 1
