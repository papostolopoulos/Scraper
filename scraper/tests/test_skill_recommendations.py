from fastapi.testclient import TestClient
from scraper.web.server import app
from pathlib import Path
import json

def test_skill_recommendations_basic(tmp_path, monkeypatch):
    client = TestClient(app)
    # Create a fake gaps details file to be discovered by /api/skill_gaps
    export_dir = tmp_path / 'exportA'
    export_dir.mkdir()
    gaps = [
        {'skill':'airflow','count':2,'shortlist_pct':0.4,'category':'workflow','priority_score':1.23},
        {'skill':'terraform','count':3,'shortlist_pct':0.6,'category':'infrastructure','priority_score':1.50}
    ]
    (export_dir / 'skill_gaps_details.json').write_text(json.dumps(gaps), encoding='utf-8')
    # Point TMP_DIR used in server to tmp_path via monkeypatch (server imports at module import time, so patch variable)
    import scraper.web.server as srv
    monkeypatch.setattr(srv, 'TMP_DIR', tmp_path)
    # Also clear token state to avoid interference
    monkeypatch.setattr(srv, 'TOKENS', {})

    r = client.get('/api/skill_recommendations?limit=5')
    assert r.status_code == 200
    data = r.json()
    assert 'recommendations' in data and isinstance(data['recommendations'], list)
    assert any('suggested_action' in rec for rec in data['recommendations']), 'Expected enrichment fields'


def test_skill_recommendations_empty(tmp_path, monkeypatch):
    client = TestClient(app)
    import scraper.web.server as srv
    monkeypatch.setattr(srv, 'TMP_DIR', tmp_path)
    monkeypatch.setattr(srv, 'TOKENS', {})
    r = client.get('/api/skill_recommendations')
    assert r.status_code == 200
    data = r.json()
    assert data['recommendations'] == []
