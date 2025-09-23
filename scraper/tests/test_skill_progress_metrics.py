import json, os, time
from pathlib import Path
from fastapi.testclient import TestClient

from scraper.web.server import app
from scraper.jobminer import skill_progress as sp


def _reset_progress():
    p = Path('scraper/data/skill_progress.json')
    if p.exists():
        p.unlink()


def test_metrics_empty():
    _reset_progress()
    client = TestClient(app)
    r = client.get('/api/skill_progress/metrics?weeks=4')
    assert r.status_code == 200
    data = r.json()
    assert 'weeks' in data and len(data['weeks']) == 4
    for w in data['weeks']:
        assert {'week_start','planned','in_progress','achieved','archived','achieved_delta'} <= set(w.keys())
    assert data['current']['achieved'] == 0
    assert data['velocity_avg_4w'] == 0


def test_metrics_progress_flow():
    _reset_progress()
    # Simulate three skills transitioning statuses
    sp.upsert_progress('SkillA', 'planned')
    time.sleep(0.01)
    sp.upsert_progress('SkillB', 'planned')
    time.sleep(0.01)
    sp.upsert_progress('SkillA', 'in_progress')
    time.sleep(0.01)
    sp.upsert_progress('SkillA', 'achieved')
    sp.upsert_progress('SkillC', 'planned')
    # Achieve SkillB later
    time.sleep(0.01)
    sp.upsert_progress('SkillB', 'in_progress')
    sp.upsert_progress('SkillB', 'achieved')
    client = TestClient(app)
    r = client.get('/api/skill_progress/metrics?weeks=2')
    assert r.status_code == 200
    data = r.json()
    assert len(data['weeks']) == 2
    # Current counts should reflect two achieved, one planned
    curr = data['current']
    assert curr['achieved'] == 2
    assert curr['planned'] >= 1  # SkillC planned
    # Velocity avg over prior full weeks is non-negative
    assert data['velocity_avg_4w'] >= 0
