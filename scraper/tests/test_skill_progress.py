from fastapi.testclient import TestClient
from scraper.web.server import app
import json

def test_progress_crud(tmp_path, monkeypatch):
    # Redirect progress file location
    import scraper.jobminer.skill_progress as sp
    monkeypatch.setattr(sp, '_PROGRESS_FILE', tmp_path / 'skill_progress.json')
    client = TestClient(app)
    # Initially empty
    r = client.get('/api/skill_progress')
    assert r.status_code == 200
    assert r.json()['count'] == 0
    # Add planned
    r = client.post('/api/skill_progress', json={'skill':'Airflow','status':'planned'})
    assert r.status_code == 200
    assert r.json()['progress']['status']=='planned'
    # Update to in_progress
    r = client.post('/api/skill_progress', json={'skill':'airflow','status':'in_progress'})
    assert r.status_code == 200
    assert r.json()['progress']['status']=='in_progress'
    # List filter
    r = client.get('/api/skill_progress?status=in_progress')
    assert r.status_code == 200
    assert r.json()['count']==1


def test_recommendations_includes_progress(tmp_path, monkeypatch):
    # Patch progress file
    import scraper.jobminer.skill_progress as sp
    monkeypatch.setattr(sp, '_PROGRESS_FILE', tmp_path / 'skill_progress.json')
    # Create fake gap details for recommendations discovery
    import scraper.web.server as srv
    monkeypatch.setattr(srv, 'TMP_DIR', tmp_path)
    (tmp_path / 'exp').mkdir()
    import json as _json
    gaps = [{'skill':'airflow','count':2,'shortlist_pct':0.5,'priority_score':1.0}]
    (tmp_path / 'exp' / 'skill_gaps_details.json').write_text(_json.dumps(gaps), encoding='utf-8')
    # Insert progress
    sp.upsert_progress('airflow','in_progress')
    client = TestClient(app)
    r = client.get('/api/skill_recommendations')
    assert r.status_code == 200
    items = r.json()['recommendations']
    assert any(i.get('progress_status')=='in_progress' for i in items)
