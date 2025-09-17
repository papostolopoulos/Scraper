from pathlib import Path
import json, os


def test_daily_snapshot_creates_files(tmp_path, monkeypatch):
    # Isolate run summary output
    monkeypatch.setenv('SCRAPER_RUN_SUMMARY', str(tmp_path / 'run_summary.json'))
    # Prepare a tiny DB in temp folder
    from scraper.jobminer.db import JobDB
    db_path = tmp_path / 'db.sqlite'
    db = JobDB(db_path)
    # Insert minimal job so snapshot has content
    from scraper.jobminer.models import JobPosting
    jp = JobPosting(job_id='snap1', title='Data Engineer', company_name='ACME', description_raw='d', description_clean='Build ETL', skills_extracted=['Python'], score_total=0.8)
    db.upsert_jobs([jp])

    # Run snapshot (no scoring)
    from scraper.scripts.daily_snapshot import compute_snapshot
    snap = compute_snapshot(db)
    assert 'jobs_total' in snap and snap['jobs_total'] >= 1
    assert 'avg_score' in snap

    # Write snapshot files via script main
    from scraper.scripts import daily_snapshot as ds
    # Redirect output dir by temporarily changing working directory if needed
    ds.append_history(snap, Path('scraper/data/daily_snapshots/history.test.jsonl'))
    # Verify history line written
    p = Path('scraper/data/daily_snapshots/history.test.jsonl')
    assert p.exists()
    line = p.read_text(encoding='utf-8').strip()
    assert line
