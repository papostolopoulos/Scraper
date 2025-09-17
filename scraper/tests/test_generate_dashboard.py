from pathlib import Path

def test_generate_dashboard_outputs_html(tmp_path):
    # Create minimal history
    hist = tmp_path / 'history.jsonl'
    hist.write_text('{"timestamp_utc":"2025-09-10T00:00:00+00:00","jobs_total":5,"avg_score":0.5,"skills_per_job":3.0}\n', encoding='utf-8')
    from scraper.scripts.generate_dashboard import load_history, prepare_series, render_html
    rows = load_history(hist)
    series = prepare_series(rows)
    html = render_html(series)
    assert '<html' in html.lower()
    assert 'Job Miner Dashboard' in html
    assert 'chart_jobs' in html
