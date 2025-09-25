from scraper.web.server import app, MERGE_STATS
from fastapi.testclient import TestClient
from scraper.jobminer.multi_source import merge_and_enrich
from scraper.jobminer.models import JobPosting
import datetime as dt
import os

def test_metrics_exposes_merge_stats(monkeypatch):
    # Enable merge
    monkeypatch.setenv('JOBMINER_ENABLE_PHASE2_MERGE','1')
    # Build a synthetic merged scenario
    jobs=[
        JobPosting(job_id='adzuna:1', title='Data Engineer', company_name='Acme', location='Remote', description_raw='Short', collected_at=dt.datetime.utcnow(), provenance=['adzuna']),
        JobPosting(job_id='lever:x', title='Data Engineer', company_name='Acme', location='Remote', description_raw='Longer body', collected_at=dt.datetime.utcnow(), provenance=['lever']),
    ]
    merged = merge_and_enrich(jobs)
    assert len(merged) == 1
    # Manually set MERGE_STATS to simulate server bookkeeping (server normally sets these during run)
    MERGE_STATS['last_before'] = 2
    MERGE_STATS['last_after'] = 1
    MERGE_STATS['dedup_saved'] = 1
    client = TestClient(app)
    resp = client.get('/api/metrics')
    assert resp.status_code == 200
    data = resp.json()
    assert data['merge_last_before'] == 2
    assert data['merge_last_after'] == 1
    assert data['merge_dedup_saved'] == 1
