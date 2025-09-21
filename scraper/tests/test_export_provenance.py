import csv
from scraper.jobminer.db import JobDB
from scraper.jobminer.exporter import Exporter
from scraper.jobminer.models import JobPosting
import datetime as dt


def test_export_includes_provenance(tmp_path):
    db_path = tmp_path / 'db.sqlite'
    db = JobDB(db_path)
    # Create a merged style job with provenance list
    job = JobPosting(
        job_id='abc123',
        title='Data Engineer',
        company_name='ExampleCo',
        location='Remote',
        work_mode='remote',
        collected_at=dt.datetime.utcnow(),
        description_raw='ETL pipelines',
        description_clean='ETL pipelines',
        employment_type='Full-time',
        seniority_level='Mid',
        skills_extracted=['Python','SQL'],
        score_total=0.75,
        score_breakdown={'skill':0.5,'semantic':0.25},
        provenance=['gh','lever'],
        status='new'
    )
    db.upsert_jobs([job])
    out_dir = tmp_path / 'out'
    exp = Exporter(db, out_dir, stream=True).export_all()
    full_csv = exp['full_csv']
    with open(full_csv, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    assert rows, 'Expected at least one exported row'
    row = rows[0]
    # Column present
    assert 'provenance' in row
    # Value is comma-joined list preserving order of input list
    assert row['provenance'] == 'gh,lever'
