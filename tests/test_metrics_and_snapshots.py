from fastapi.testclient import TestClient
from scraper.web import server as srv
from scraper.web.server import app, JobRun
from datetime import datetime, timezone, timedelta
import json


def test_api_metrics_basic_aggregates(monkeypatch):
    # Isolate in-memory state
    with srv.JOBS_LOCK:
        srv.JOBS.clear()
    with srv.EVENTS_LOCK:
        srv.EVENTS.clear()
    # Seed a few jobs with timings
    now = datetime.now(timezone.utc)
    j1 = JobRun(job_id='j1', created=now, status='done', timings={'fetch_sec': 1.0, 'scoring_sec': 2.0, 'export_sec': 0.5, 'total_sec': 3.5})
    j2 = JobRun(job_id='j2', created=now, status='error', timings={'fetch_sec': 2.0, 'scoring_sec': 1.0, 'export_sec': 0.5, 'total_sec': 3.5})
    j3 = JobRun(job_id='j3', created=now, status='running', timings={'fetch_sec': 1.0})  # Active job
    j4 = JobRun(job_id='j4', created=now, status='pending', timings={})  # Active job
    with srv.JOBS_LOCK:
        srv.JOBS[j1.job_id] = j1
        srv.JOBS[j2.job_id] = j2
        srv.JOBS[j3.job_id] = j3
        srv.JOBS[j4.job_id] = j4
    client = TestClient(app)
    r = client.get('/api/metrics')
    assert r.status_code == 200
    data = r.json()
    # Totals and statuses
    assert data['jobs']['total'] == 4
    assert data['jobs']['active'] == 2  # running + pending jobs
    assert data['statuses'].get('done', 0) == 1
    assert data['statuses'].get('error', 0) == 1
    assert data['statuses'].get('running', 0) == 1
    assert data['statuses'].get('pending', 0) == 1
    # Averages (where present)
    assert data['avg_fetch_sec'] == 1.333 or abs(data['avg_fetch_sec'] - 1.333) < 0.001
    assert data['avg_scoring_sec'] == 1.5 or abs(data['avg_scoring_sec'] - 1.5) < 0.001
    assert data['avg_export_sec'] == 0.5
    assert data['avg_total_sec'] == 3.5


def test_snapshot_append_and_prune(tmp_path, monkeypatch):
    # Point TMP_DIR so metrics snapshot writer writes to an isolated path
    monkeypatch.setattr('scraper.web.server.TMP_DIR', tmp_path)
    # Reduce retention for test
    monkeypatch.setattr('scraper.web.server.SNAPSHOT_MAX_LINES', 5)
    monkeypatch.setattr('scraper.web.server.SNAPSHOT_MAX_AGE_DAYS', 1)
    # Ensure empty state
    snap_file = tmp_path / 'snapshots' / 'jobminer_daily.jsonl'
    if snap_file.exists():
        snap_file.unlink()
    client = TestClient(app)
    # Make several metrics calls to append snapshots
    for _ in range(7):
        r = client.get('/api/metrics')
        assert r.status_code == 200
    # Verify file exists and pruned to max lines
    assert snap_file.exists()
    lines = snap_file.read_text(encoding='utf-8').splitlines()
    assert len(lines) <= 5
    # Entries should be valid JSON
    for ln in lines:
        obj = json.loads(ln)
        assert 'jobs' in obj and 'statuses' in obj
