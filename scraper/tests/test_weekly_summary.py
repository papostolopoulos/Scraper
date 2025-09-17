from pathlib import Path
import json


def test_weekly_summary_markdown(tmp_path):
    # Build a tiny history.jsonl
    hist = tmp_path / 'history.jsonl'
    rows = [
        {"timestamp_utc": "2025-09-10T00:00:00+00:00", "jobs_total": 10, "avg_score": 0.6, "skills_per_job": 4.0, "top_titles": ["Data Engineer"]},
        {"timestamp_utc": "2025-09-11T00:00:00+00:00", "jobs_total": 12, "avg_score": 0.62, "skills_per_job": 4.2, "top_titles": ["Data Engineer","ML Engineer"]},
    ]
    with hist.open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    from scraper.scripts.weekly_summary import load_history, summarize, render_markdown
    loaded = load_history(hist)
    assert len(loaded) == 2
    summary = summarize(loaded)
    assert summary['runs'] == 2
    md = render_markdown(summary)
    assert '# Weekly Summary' in md
    assert 'Runs: 2' in md
