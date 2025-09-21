from __future__ import annotations
import csv
from pathlib import Path
from scraper.jobminer.db import JobDB
from scraper.jobminer.models import JobPosting
from scraper.jobminer.exporter import Exporter
import datetime as dt

def test_full_export_includes_provenance_non_streaming(tmp_path: Path):
    db = JobDB(tmp_path / 'test.sqlite')
    job = JobPosting(
        job_id='m1',
        title='Machine Learning Engineer',
        company_name='ExampleCo',
        location='Remote',
        description_clean='ML systems and pipelines',
        skills_extracted=['python','ml'],
        score_total=0.82,
        score_breakdown={'skill':0.5,'semantic':0.32},
        provenance=['gh','lever'],
    )
    db.upsert_jobs([job])
    exporter = Exporter(db, tmp_path, stream=False)
    outputs = exporter.export_all()
    full_csv = outputs['full_csv']
    with open(full_csv, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    assert rows and rows[0].get('provenance') == 'gh,lever'
