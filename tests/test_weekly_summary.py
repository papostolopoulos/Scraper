import json, tempfile, datetime as dt
from pathlib import Path
from scripts.weekly_summary import load_runs, summarize, render


def make_run(ts: dt.datetime, status='done', count=10, limit=50, eff=0.4):
    return {
        'ts': ts.isoformat().replace('+00:00','Z'),
        'status': status,
        'count': count,
        'limit': limit,
        'timings': {
            'fetch_sec': 1.2,
            'scoring_sec': 0.5,
            'export_sec': 0.2,
            'total_sec': 2.1,
        },
        'merge': {
            'effectiveness': eff,
        },
        'query_title': 'data scientist'
    }


def test_summarize_basic():
    now = dt.datetime.now(dt.timezone.utc)
    runs = [make_run(now - dt.timedelta(hours=i), eff=0.3 + i*0.01) for i in range(5)]
    summary = summarize(list(reversed(runs)))
    assert summary['total_runs'] == 5
    assert summary['success_runs'] == 5
    assert summary['merge_eff_min'] is not None
    assert summary['top_titles'][0][0] == 'data scientist'


def test_render_empty():
    now = dt.datetime.now(dt.timezone.utc)
    md = render({'empty': True}, now-dt.timedelta(days=7), now)
    assert 'No runs' in md


def test_load_runs_filters_age(tmp_path: Path):
    snap = tmp_path / 'runs.jsonl'
    now = dt.datetime.now(dt.timezone.utc)
    recent = make_run(now - dt.timedelta(days=2))
    old = make_run(now - dt.timedelta(days=10))
    with snap.open('w', encoding='utf-8') as fh:
        fh.write(json.dumps(recent)+'\n')
        fh.write(json.dumps(old)+'\n')
    loaded = load_runs(snap, days=7)
    assert len(loaded) == 1
    assert loaded[0]['ts'] == recent['ts']
