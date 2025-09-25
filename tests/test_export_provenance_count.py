from scraper.jobminer.exporter import Exporter
from scraper.jobminer.db import JobDB
from scraper.jobminer.models import JobPosting
from pathlib import Path
import datetime as dt
import csv

def test_export_includes_provenance_count(tmp_path):
    db_path = tmp_path / 'db.sqlite'
    db = JobDB(db_path)
    job = JobPosting(
        job_id='adzuna:1',
        title='Data Engineer',
        company_name='Acme',
        location='Remote',
        description_raw='x',
        description_clean='x',
        collected_at=dt.datetime.utcnow(),
        provenance=['adzuna','lever','greenhouse']
    )
    db.upsert_jobs([job])
    export_dir = tmp_path / 'out'
    exp = Exporter(db, export_dir, stream=True)
    artifacts = exp.export_all()
    full_csv = artifacts['full_csv']
    with open(full_csv, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert rows
    r = rows[0]
    assert 'provenance_count' in r
    assert r['provenance'] == 'adzuna,lever,greenhouse'
    assert int(r['provenance_count']) == 3
