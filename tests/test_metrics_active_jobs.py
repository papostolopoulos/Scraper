from fastapi.testclient import TestClient
from scraper.web import server as srv
from scraper.web.server import app, JobRun
from datetime import datetime, timezone


def test_active_jobs_count_accuracy(monkeypatch):
    """Test that active_jobs count correctly distinguishes between active and completed jobs."""
    # Isolate in-memory state
    with srv.JOBS_LOCK:
        srv.JOBS.clear()
    with srv.EVENTS_LOCK:
        srv.EVENTS.clear()
    
    now = datetime.now(timezone.utc)
    # Create jobs with different statuses
    jobs = [
        JobRun(job_id='done1', created=now, status='done'),          # Not active
        JobRun(job_id='done2', created=now, status='done'),          # Not active
        JobRun(job_id='error1', created=now, status='error'),        # Not active  
        JobRun(job_id='cancelled1', created=now, status='cancelled'), # Not active
        JobRun(job_id='running1', created=now, status='running'),    # Active
        JobRun(job_id='pending1', created=now, status='pending'),    # Active
        JobRun(job_id='fetching1', created=now, status='fetching'),  # Active
    ]
    
    with srv.JOBS_LOCK:
        for job in jobs:
            srv.JOBS[job.job_id] = job
    
    client = TestClient(app)
    r = client.get('/api/metrics')
    assert r.status_code == 200
    data = r.json()
    
    # Verify counts
    assert data['jobs']['total'] == 7, f"Expected total 7, got {data['jobs']['total']}"
    assert data['jobs']['active'] == 3, f"Expected active 3, got {data['jobs']['active']}"
    
    # Verify status breakdown
    assert data['statuses'].get('done', 0) == 2
    assert data['statuses'].get('error', 0) == 1
    assert data['statuses'].get('cancelled', 0) == 1
    assert data['statuses'].get('running', 0) == 1
    assert data['statuses'].get('pending', 0) == 1
    assert data['statuses'].get('fetching', 0) == 1


def test_active_jobs_empty_state():
    """Test active_jobs count when no jobs exist."""
    # Isolate in-memory state
    with srv.JOBS_LOCK:
        srv.JOBS.clear()
    with srv.EVENTS_LOCK:
        srv.EVENTS.clear()
    
    client = TestClient(app)
    r = client.get('/api/metrics')
    assert r.status_code == 200
    data = r.json()
    
    # Should have zero for both counts
    assert data['jobs']['total'] == 0
    assert data['jobs']['active'] == 0
    assert data['statuses'] == {}


def test_active_jobs_all_done():
    """Test active_jobs count when all jobs are completed."""
    # Isolate in-memory state
    with srv.JOBS_LOCK:
        srv.JOBS.clear()
    with srv.EVENTS_LOCK:
        srv.EVENTS.clear()
    
    now = datetime.now(timezone.utc)
    jobs = [
        JobRun(job_id='done1', created=now, status='done'),
        JobRun(job_id='error1', created=now, status='error'),
        JobRun(job_id='cancelled1', created=now, status='cancelled'),
    ]
    
    with srv.JOBS_LOCK:
        for job in jobs:
            srv.JOBS[job.job_id] = job
    
    client = TestClient(app)
    r = client.get('/api/metrics')
    assert r.status_code == 200
    data = r.json()
    
    # Should have zero active jobs
    assert data['jobs']['total'] == 3
    assert data['jobs']['active'] == 0