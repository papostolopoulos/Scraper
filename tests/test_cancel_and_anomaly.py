import json, time, datetime as dt
from pathlib import Path
from fastapi.testclient import TestClient
from scraper.web.server import app, JOBS, _persist_job, TMP_DIR

client = TestClient(app)


def test_cancel_flow(monkeypatch, tmp_path):
    # Create a lightweight job by mocking AdzunaSource fetch -> empty list and score_all -> sleep loop
    from scraper.web import server as srv
    class DummySrc:
        def __init__(self, **kw): pass
        def fetch(self): return []
    monkeypatch.setattr(srv, 'AdzunaSource', DummySrc)
    monkeypatch.setenv('ADZUNA_APP_ID','x'); monkeypatch.setenv('ADZUNA_APP_KEY','y')

    # Submit job
    resume_path = tmp_path / 'r.pdf'; resume_path.write_text('dummy')
    files = {'resume': ('r.pdf', resume_path.read_bytes(), 'application/pdf')}
    data = {'title':'Data','location':'NY','distance':'10','limit':'10','country':'us'}
    r = client.post('/api/jobs', data=data, files=files)
    assert r.status_code==200
    job_id = r.json()['job_id']

    # Cancel immediately
    rc = client.post(f'/api/jobs/{job_id}/cancel')
    assert rc.status_code==200

    # Poll until cancelled or done
    for _ in range(30):
        rs = client.get(f'/api/jobs/{job_id}')
        st = rs.json()['status']
        if st in ('cancelled','done','error'): break
        time.sleep(0.1)
    assert st=='cancelled'


def test_sustained_low_merge_anomaly(tmp_path, monkeypatch):
    # Build synthetic runs.jsonl with merge effectiveness high then degraded
    snap_dir = TMP_DIR / 'snapshots'
    snap_dir.mkdir(parents=True, exist_ok=True)
    f = snap_dir / 'runs.jsonl'
    lines = []
    base_ts = dt.datetime.now(dt.timezone.utc)
    # 9 historical high values ~0.5
    for i in range(9):
        lines.append(json.dumps({'ts': (base_ts - dt.timedelta(minutes=9-i)).isoformat(), 'status':'done','count':10,'limit':10,'timings':{},'merge':{'effectiveness':0.5,'before':20,'after':10,'saved':10}}))
    # Latest low value 0.1
    lines.append(json.dumps({'ts': base_ts.isoformat(),'status':'done','count':10,'limit':10,'timings':{},'merge':{'effectiveness':0.1,'before':20,'after':18,'saved':2}}))
    f.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    r = client.get('/api/health/summary')
    data = r.json()
    types = {a['type'] for a in data.get('anomalies',[])}
    assert 'merge_effectiveness_sustained_low' in types
