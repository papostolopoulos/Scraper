from pathlib import Path

from scraper.web.server import app
from fastapi.testclient import TestClient


def test_metrics_empty_state_writes_snapshot(tmp_path, monkeypatch):
    # Isolate TMP_DIR and force small retention
    monkeypatch.setattr('scraper.web.server.TMP_DIR', tmp_path)
    monkeypatch.setattr('scraper.web.server.SNAPSHOT_MAX_LINES', 3)
    monkeypatch.setattr('scraper.web.server.SNAPSHOT_MAX_AGE_DAYS', 30)

    client = TestClient(app)
    r = client.get('/api/metrics')
    assert r.status_code == 200
    body = r.json()
    assert 'jobs' in body and body['jobs']['total'] == 0
    # Snapshot should be written under TMP_DIR/snapshots
    snap = tmp_path / 'snapshots' / 'jobminer_daily.jsonl'
    assert snap.exists(), 'daily snapshot should be created on metrics call'
    assert snap.stat().st_size > 0
