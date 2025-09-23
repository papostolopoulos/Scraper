import json
from fastapi.testclient import TestClient
from scraper.web.server import app, JobRun, _register_job, _process_job
from datetime import datetime, timezone
import uuid

client = TestClient(app)

def test_health_summary_structure():
    # Just call endpoint when no snapshots maybe exist
    resp = client.get('/api/health/summary')
    assert resp.status_code == 200
    data = resp.json()
    assert 'runs' in data
    assert 'averages' in data
    assert 'anomalies' in data

