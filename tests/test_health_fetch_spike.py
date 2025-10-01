from fastapi.testclient import TestClient
from scraper.web.server import app, TMP_DIR
from datetime import datetime, timezone
import json, uuid


def _line(ts, fetch):
    return {
        'ts': ts.isoformat(),
        'job_id': uuid.uuid4().hex,
        'status': 'done',
        'count': 5,
        'limit': 5,
        'timings': {'fetch_sec': fetch, 'scoring_sec': 0.5, 'export_sec': 0.1, 'total_sec': 0.6},
    }


def test_fetch_time_spike_anomaly(tmp_path, monkeypatch):
    monkeypatch.setattr('scraper.web.server.TMP_DIR', tmp_path)
    snap = tmp_path / 'snapshots'; snap.mkdir(parents=True, exist_ok=True)
    f = snap / 'runs.jsonl'
    now = datetime.now(timezone.utc)
    lines = []
    # Prior stable fetch times
    for i in range(6):
        lines.append(_line(now, fetch=0.5))
    # Spike
    lines.append(_line(now, fetch=1.0))
    f.write_text('\n'.join(json.dumps(x) for x in lines) + '\n', encoding='utf-8')
    client = TestClient(app)
    r = client.get('/api/health/summary?limit=20')
    assert r.status_code == 200
    data = r.json()
    types = {a['type'] for a in data.get('anomalies', [])}
    assert 'fetch_sec_spike' in types
