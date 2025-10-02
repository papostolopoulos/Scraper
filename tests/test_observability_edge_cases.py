from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
from scraper.web.snapshot import SnapshotWriter
from scraper.web.server import app
from fastapi.testclient import TestClient


def test_snapshot_prune_age(tmp_path: Path):
    # Write 3 lines: two old, one fresh; prune with max_age_days=0 should keep only fresh
    sw = SnapshotWriter(path=tmp_path / 'jobminer_daily.jsonl')
    # Manually craft timestamps
    old = {'jobs': {'total': 1}, 'ts': (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()}
    fresh = {'jobs': {'total': 2}, 'ts': datetime.now(timezone.utc).isoformat()}
    # Bypass append to control ts
    p = tmp_path / 'jobminer_daily.jsonl'
    p.write_text('\n'.join(json.dumps(d) for d in [old, old, fresh]), encoding='utf-8')
    sw.prune(max_lines=100, max_age_days=0)
    kept = [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
    assert len(kept) == 1 and kept[0]['jobs']['total'] == 2


def test_metrics_with_no_jobs_and_mixed_statuses(monkeypatch, tmp_path: Path):
    # Isolate snapshot dir and TMP_DIR so endpoint can write
    monkeypatch.setenv('JOBMINER_SNAPSHOT_DIR', str(tmp_path))
    client = TestClient(app)
    r = client.get('/api/metrics')
    assert r.status_code == 200
    data = r.json()
    assert data['jobs']['total'] == 0
    # Simulate mixed statuses via event log tail by calling several endpoints
    client.get('/')  # 404 but still logs request events
    r2 = client.get('/api/metrics')
    assert r2.status_code == 200
    d2 = r2.json()
    assert 'event_tail' in d2 and isinstance(d2['event_tail'], list)
