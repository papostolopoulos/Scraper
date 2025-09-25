from scraper.web.server import app, MERGE_STATS
from fastapi.testclient import TestClient

def test_merge_effectiveness_metric():
    MERGE_STATS['last_before'] = 10
    MERGE_STATS['last_after'] = 7
    MERGE_STATS['dedup_saved'] = 3
    client = TestClient(app)
    resp = client.get('/api/metrics')
    assert resp.status_code == 200
    data = resp.json()
    assert data['merge_last_before'] == 10
    assert data['merge_dedup_saved'] == 3
    assert data['merge_effectiveness'] == round(3/10,3)
