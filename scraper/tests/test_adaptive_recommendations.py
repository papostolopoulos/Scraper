from fastapi.testclient import TestClient
from scraper.web.server import app
import json

def setup_gap(tmp_path, monkeypatch, gaps):
    import scraper.web.server as srv
    monkeypatch.setattr(srv, 'TMP_DIR', tmp_path)
    (tmp_path / 'exp').mkdir()
    (tmp_path / 'exp' / 'skill_gaps_details.json').write_text(json.dumps(gaps), encoding='utf-8')

def test_adaptive_filters_achieved_and_blocks(tmp_path, monkeypatch):
    # Prepare gaps with hierarchical skills
    gaps = [
        {'skill':'airflow','count':3,'shortlist_pct':0.6,'priority_score':1.5},
        {'skill':'airflow advanced','count':2,'shortlist_pct':0.4,'priority_score':1.4},
        {'skill':'sql','count':4,'shortlist_pct':0.8,'priority_score':1.7},
        {'skill':'sql optimization','count':2,'shortlist_pct':0.5,'priority_score':1.6}
    ]
    setup_gap(tmp_path, monkeypatch, gaps)
    # Patch progress file
    import scraper.jobminer.skill_progress as sp
    monkeypatch.setattr(sp, '_PROGRESS_FILE', tmp_path / 'skill_progress.json')
    sp.upsert_progress('airflow','achieved')
    sp.upsert_progress('sql','in_progress')
    client = TestClient(app)
    r = client.get('/api/skill_recommendations?limit=10')
    assert r.status_code == 200
    data = r.json()['recommendations']
    # Achieved airflow should be absent
    assert all(rec['skill'].lower() != 'airflow' for rec in data)
    # Advanced airflow should be blocked (depends on airflow) but airflow achieved -> so not blocked
    adv = next(rec for rec in data if rec['skill'].lower()=='airflow advanced')
    assert 'blocked_by' not in adv  # prerequisite achieved
    # sql optimization should show blocked_by if sql not achieved yet (only in_progress)
    sql_opt = next(rec for rec in data if rec['skill'].lower()=='sql optimization')
    assert 'blocked_by' in sql_opt and 'sql' in sql_opt['blocked_by']


def test_in_progress_demoted(tmp_path, monkeypatch):
    gaps = [
        {'skill':'terraform','count':3,'shortlist_pct':0.5,'priority_score':1.5},
        {'skill':'spark','count':3,'shortlist_pct':0.5,'priority_score':1.5}
    ]
    setup_gap(tmp_path, monkeypatch, gaps)
    import scraper.jobminer.skill_progress as sp
    monkeypatch.setattr(sp, '_PROGRESS_FILE', tmp_path / 'skill_progress.json')
    sp.upsert_progress('terraform','in_progress')
    client = TestClient(app)
    r = client.get('/api/skill_recommendations?limit=2')
    assert r.status_code == 200
    recs = r.json()['recommendations']
    # With identical priority, the in_progress item should appear after the untouched one
    assert recs[0]['skill'].lower() == 'spark'
