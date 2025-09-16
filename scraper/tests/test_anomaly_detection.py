from pathlib import Path
import json, tempfile
from scraper.jobminer.anomaly import detect_anomalies
from scraper.jobminer.history import append_history


def write_runs(path: Path, avg_scores, skills_rates):
    for s,r in zip(avg_scores, skills_rates):
        append_history({'avg_score': s, 'skills_per_job': r, 'jobs_processed': 5}, path)


def test_no_warning_with_small_baseline(tmp_path):
    hist = tmp_path/"hist.jsonl"
    write_runs(hist, [0.6,0.61,0.59], [5.0,5.1,5.2])  # only 3 runs, need >=6
    assert detect_anomalies(hist) == []


def test_avg_score_drop_triggers(tmp_path):
    hist = tmp_path/"hist2.jsonl"
    # 5 baseline runs around 0.6 then a big drop to 0.3 (>35%)
    write_runs(hist, [0.60,0.62,0.61,0.59,0.60,0.30], [5.0,5.1,5.2,5.0,5.1,5.0])
    warns = detect_anomalies(hist)
    assert any('Average score drop' in w for w in warns)


def test_skills_rate_drop_triggers(tmp_path):
    hist = tmp_path/"hist3.jsonl"
    write_runs(hist, [0.60,0.62,0.61,0.59,0.60,0.59], [5.0,5.1,5.2,5.0,5.1,2.5])
    warns = detect_anomalies(hist)
    assert any('Skills per job drop' in w for w in warns)
