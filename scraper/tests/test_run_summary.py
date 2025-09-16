from pathlib import Path
import json, os, time
from scraper.jobminer.db import JobDB
from scraper.jobminer.pipeline import score_all
from scraper.jobminer.models import JobPosting


def test_run_summary_written(tmp_path, monkeypatch):
    # Setup temp DB
    db_path = tmp_path / 'db.sqlite'
    monkeypatch.setenv('SCRAPER_RUN_SUMMARY', str(tmp_path / 'run_summary.json'))
    db = JobDB(db_path)
    # Insert mock job
    jp = JobPosting(job_id='1', title='Data Engineer', company_name='ACME', description_raw='We use Python and SQL', description_clean='We use Python and SQL')
    db.upsert_jobs([jp])
    resume_pdf = Path('Resume - Paris_Apostolopoulos.pdf')  # existing file in repo root
    seed_skills_file = tmp_path / 'skills.txt'
    seed_skills_file.write_text('Python\nSQL\nETL', encoding='utf-8')
    # If resume PDF missing in CI, skip gracefully
    if not resume_pdf.exists():
        # create lightweight dummy PDF fallback
        dummy = tmp_path / 'dummy.pdf'
        dummy.write_bytes(b"%PDF-1.3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF")
        resume_pdf = dummy
    count = score_all(db, resume_pdf, seed_skills_file, write_summary=True)
    assert count == 1
    summary_path = Path(os.getenv('SCRAPER_RUN_SUMMARY'))
    assert summary_path.exists()
    data = json.loads(summary_path.read_text(encoding='utf-8'))
    assert data['jobs_processed'] == 1
    assert 'timings' in data and 'scoring_s' in data['timings']
    assert data['skill_cache_hits'] >= 0
