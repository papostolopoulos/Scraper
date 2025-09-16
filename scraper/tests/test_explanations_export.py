from __future__ import annotations
from pathlib import Path
from scraper.jobminer.db import JobDB
from scraper.jobminer.models import JobPosting
from scraper.jobminer.exporter import Exporter


def test_explanations_csv_export(tmp_path: Path):
    db = JobDB(str(tmp_path / 'test.sqlite'))
    job = JobPosting(
        job_id='1',
        title='Data Engineer',
        company_name='ExampleCo',
        description_clean='Build data pipelines',
        skills_extracted=['python','sql','etl'],
        score_total=0.75,
        score_breakdown={'skill':0.6,'semantic':0.5,'recency':0.8,'seniority_component':1.0},
        benefits=['health'],
    )
    db.upsert_jobs([job])
    exporter = Exporter(db, tmp_path)
    outputs = exporter.export_all()
    expl = outputs.get('explanations_csv')
    assert expl is not None and Path(expl).exists()
    content = Path(expl).read_text(encoding='utf-8').splitlines()
    assert 'job_id,title,company_name' in content[0]
    assert ',Data Engineer,' in content[1]