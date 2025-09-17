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


def test_run_summary_includes_semantic_benchmark_when_enabled(tmp_path, monkeypatch):
    # Setup temp DB and env to write summary to tmp
    db_path = tmp_path / 'db.sqlite'
    monkeypatch.setenv('SCRAPER_RUN_SUMMARY', str(tmp_path / 'run_summary.json'))
    # Enable benchmark with small limit for speed
    monkeypatch.setenv('SCRAPER_SEMANTIC_BENCH', '1')
    monkeypatch.setenv('SCRAPER_SEMANTIC_BENCH_LIMIT', '1')
    db = JobDB(db_path)
    # Insert minimal job data
    jp = JobPosting(job_id='b1', title='Data Engineer', company_name='ACME', description_raw='We use Python and SQL', description_clean='We use Python and SQL')
    db.upsert_jobs([jp])
    # Lightweight resume/seed
    resume_pdf = tmp_path / 'dummy.pdf'
    resume_pdf.write_bytes(b"%PDF-1.3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF")
    seed_skills_file = tmp_path / 'skills.txt'
    seed_skills_file.write_text('Python\nSQL', encoding='utf-8')
    count = score_all(db, resume_pdf, seed_skills_file, write_summary=True)
    assert count == 1
    summary_path = Path(os.getenv('SCRAPER_RUN_SUMMARY'))
    data = json.loads(summary_path.read_text(encoding='utf-8'))
    # Verify benchmark section present and contains expected keys
    assert 'semantic_benchmark' in data
    bench = data['semantic_benchmark']
    for k in ['sampled_jobs', 'heuristic_time_s', 'semantic_time_s', 'avg_skills_heuristic', 'avg_skills_semantic']:
        assert k in bench


def test_run_summary_omits_semantic_benchmark_when_disabled(tmp_path, monkeypatch):
    db_path = tmp_path / 'db.sqlite'
    monkeypatch.setenv('SCRAPER_RUN_SUMMARY', str(tmp_path / 'run_summary.json'))
    # Ensure disabled
    if 'SCRAPER_SEMANTIC_BENCH' in os.environ:
        monkeypatch.delenv('SCRAPER_SEMANTIC_BENCH', raising=False)
    if 'SCRAPER_SEMANTIC_BENCH_LIMIT' in os.environ:
        monkeypatch.delenv('SCRAPER_SEMANTIC_BENCH_LIMIT', raising=False)
    db = JobDB(db_path)
    jp = JobPosting(job_id='c1', title='Data Engineer', company_name='ACME', description_raw='We use Python and SQL', description_clean='We use Python and SQL')
    db.upsert_jobs([jp])
    resume_pdf = tmp_path / 'dummy.pdf'
    resume_pdf.write_bytes(b"%PDF-1.3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF")
    seed_skills_file = tmp_path / 'skills.txt'
    seed_skills_file.write_text('Python\nSQL', encoding='utf-8')
    count = score_all(db, resume_pdf, seed_skills_file, write_summary=True)
    assert count == 1
    summary_path = Path(os.getenv('SCRAPER_RUN_SUMMARY'))
    data = json.loads(summary_path.read_text(encoding='utf-8'))
    assert 'semantic_benchmark' not in data
