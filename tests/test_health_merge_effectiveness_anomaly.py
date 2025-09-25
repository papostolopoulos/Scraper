from scraper.web.server import app, TMP_DIR
from fastapi.testclient import TestClient
from datetime import datetime, timezone
import json, uuid


def _write_run(fh, eff):
    before = 20
    after = int(before * (1-eff)) if eff is not None else 15
    saved = before - after
    rec = {
        'ts': datetime.now(timezone.utc).isoformat(),
        'job_id': uuid.uuid4().hex,
        'status': 'done',
        'error': None,
        'count': after,
        'limit': before,
        'timings': {'fetch_sec': 1.0, 'scoring_sec': 2.0, 'export_sec': 0.5, 'total_sec': 3.5},
        'merge': {
            'before': before,
            'after': after,
            'saved': saved,
            'effectiveness': round(saved/before,3)
        }
    }
    fh.write(json.dumps(rec)+'\n')


def test_merge_effectiveness_drop_anomaly(tmp_path, monkeypatch):
    monkeypatch.setattr('scraper.web.server.TMP_DIR', tmp_path)
    snap_dir = tmp_path / 'snapshots'
    snap_dir.mkdir(parents=True, exist_ok=True)
    runs_file = snap_dir / 'runs.jsonl'
    # Write 7 stable runs with effectiveness ~0.4 then one with 0.05
    with open(runs_file, 'w', encoding='utf-8') as fh:
        for _ in range(7):
            _write_run(fh, 0.4)
        # Drastically lower effectiveness run
        _write_run(fh, 0.05)
    client = TestClient(app)
    resp = client.get('/api/health/summary?limit=20')
    assert resp.status_code == 200
    data = resp.json()
    anomaly_types = {a['type'] for a in data.get('anomalies', [])}
    assert 'merge_effectiveness_drop' in anomaly_types
