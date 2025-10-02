from fastapi.testclient import TestClient
from scraper.web.server import app
from datetime import datetime, timezone, timedelta
import json, uuid


def _run_rec(ts, status='done', count=10, limit=10, fetch=0.8):
    return {
        'ts': ts.isoformat(),
        'job_id': uuid.uuid4().hex,
        'status': status,
        'error': None if status != 'error' else 'boom',
        'count': count,
        'limit': limit,
        'timings': {'fetch_sec': fetch, 'scoring_sec': 1.0, 'export_sec': 0.2, 'total_sec': 1.2},
    }


def test_zero_jobs_streak_anomaly(tmp_path, monkeypatch):
    monkeypatch.setattr('scraper.web.server.TMP_DIR', tmp_path)
    snap = tmp_path / 'snapshots'; snap.mkdir(parents=True, exist_ok=True)
    f = snap / 'runs.jsonl'
    now = datetime.now(timezone.utc)
    lines = []
    # Some successful runs with counts > 0
    for i in range(4):
        lines.append(json.dumps(_run_rec(now - timedelta(minutes=20 - i), status='done', count=5, limit=10)))
    # Append 3 consecutive zeros at the end to trigger streak >=3
    for i in range(3):
        lines.append(json.dumps(_run_rec(now - timedelta(minutes=3 - i), status='done', count=0, limit=10)))
    f.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    client = TestClient(app)
    r = client.get('/api/health/summary?limit=20')
    assert r.status_code == 200
    data = r.json()
    types = {a['type'] for a in data.get('anomalies', [])}
    assert 'zero_jobs_streak' in types


def test_error_rate_high_anomaly(tmp_path, monkeypatch):
    monkeypatch.setattr('scraper.web.server.TMP_DIR', tmp_path)
    snap = tmp_path / 'snapshots'; snap.mkdir(parents=True, exist_ok=True)
    f = snap / 'runs.jsonl'
    now = datetime.now(timezone.utc)
    recs = []
    # 7 runs total: 3 errors -> error_rate ~0.43 (>0.3), total>=5
    for i in range(4):
        recs.append(_run_rec(now - timedelta(minutes=10 - i), status='done', count=5, limit=10))
    for i in range(3):
        recs.append(_run_rec(now - timedelta(minutes=3 - i), status='error', count=0, limit=10))
    f.write_text('\n'.join(json.dumps(r) for r in recs) + '\n', encoding='utf-8')
    client = TestClient(app)
    r = client.get('/api/health/summary?limit=20')
    assert r.status_code == 200
    data = r.json()
    types = {a['type'] for a in data.get('anomalies', [])}
    assert 'error_rate_high' in types
