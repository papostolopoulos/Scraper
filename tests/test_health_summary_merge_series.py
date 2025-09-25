from scraper.web.server import app, TMP_DIR, MERGE_STATS
from fastapi.testclient import TestClient
from datetime import datetime, timezone
import json, uuid


def test_health_summary_merge_series(tmp_path, monkeypatch):
    # Point TMP_DIR to temp path for isolated snapshot file
    monkeypatch.setattr('scraper.web.server.TMP_DIR', tmp_path)
    snap_dir = tmp_path / 'snapshots'
    snap_dir.mkdir(parents=True, exist_ok=True)
    runs_file = snap_dir / 'runs.jsonl'
    # Simulate three runs with merge stats
    for before, after in [(20,15),(18,12),(25,10)]:
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
        with open(runs_file, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(rec)+'\n')
    client = TestClient(app)
    resp = client.get('/api/health/summary?limit=10')
    assert resp.status_code == 200
    data = resp.json()
    assert 'merge_series' in data
    assert len(data['merge_series']) == 3
    eff_vals = [m['effectiveness'] for m in data['merge_series']]
    assert all(e is not None for e in eff_vals)
    averages = data['averages']
    assert 'merge_effectiveness_avg' in averages
    assert averages['merge_effectiveness_avg'] is not None
