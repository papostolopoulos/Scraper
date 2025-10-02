import datetime as dt
from pathlib import Path
import csv
from scraper.jobminer.db import JobDB
from scraper.jobminer.models import JobPosting
from scraper.jobminer.exporter import Exporter


def test_exporter_fallback_apply_url_and_benefits(tmp_path: Path):
    db = JobDB(tmp_path/'db.sqlite')
    job = JobPosting(
        job_id='12345',
        title='Engineer',
        company_name='Acme',
        collected_at=dt.datetime.utcnow(),
        description_clean='Build systems',
        benefits=[],
        status='new',
    )
    # Missing apply_url should fallback to LinkedIn pattern
    db.upsert_jobs([job])
    out_dir = tmp_path/'out'
    exp = Exporter(db, out_dir, stream=True).export_all()
    with open(exp['full_csv'], newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    assert rows[0]['apply_url'].startswith('https://www.linkedin.com/jobs/view/12345')
    # benefits_normalized column present (empty -> None)
    assert 'benefits_normalized' in rows[0]
