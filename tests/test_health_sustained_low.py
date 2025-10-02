from fastapi.testclient import TestClient
from scraper.web.server import app
from datetime import datetime, timezone, timedelta
import json, uuid


def test_merge_effectiveness_sustained_low_isolated(tmp_path, monkeypatch):
    # Isolate snapshot storage
    monkeypatch.setattr('scraper.web.server.TMP_DIR', tmp_path)
    snap = tmp_path / 'snapshots'; snap.mkdir(parents=True, exist_ok=True)
    runs = snap / 'runs.jsonl'
    now = datetime.now(timezone.utc)
    lines = []
    # 9 historical runs with effectiveness ~0.5 (median > 0.30)
    for i in range(9):
        eff = 0.5
        before = 20
        saved = int(before * eff)
        after = before - saved
        rec = {
            'ts': (now - timedelta(minutes=10-i)).isoformat(),
            'job_id': uuid.uuid4().hex,
            'status': 'done',
            'count': after,
            'limit': before,
            'timings': {'fetch_sec': 0.8, 'scoring_sec': 1.2, 'export_sec': 0.3, 'total_sec': 2.3},
            'merge': {'before': before, 'after': after, 'saved': saved, 'effectiveness': round(saved/before,3)},
        }
        lines.append(json.dumps(rec))
    # Latest sustained low effectiveness < 0.15
    before = 20
    saved = 2  # 0.10 effectiveness
    after = before - saved
    rec = {
        'ts': now.isoformat(),
        'job_id': uuid.uuid4().hex,
        'status': 'done',
        'count': after,
        'limit': before,
        'timings': {'fetch_sec': 0.9, 'scoring_sec': 1.1, 'export_sec': 0.2, 'total_sec': 2.2},
        'merge': {'before': before, 'after': after, 'saved': saved, 'effectiveness': round(saved/before,3)},
    }
    lines.append(json.dumps(rec))
    runs.write_text("\n".join(lines) + "\n", encoding='utf-8')

    client = TestClient(app)
    r = client.get('/api/health/summary?limit=20')
    assert r.status_code == 200
    data = r.json()
    types = {a['type'] for a in data.get('anomalies', [])}
    assert 'merge_effectiveness_sustained_low' in types
