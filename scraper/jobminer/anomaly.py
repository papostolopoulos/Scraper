"""Simple anomaly detection on run history.

Heuristics:
 - Average score drop: compare last run avg_score to mean of previous N runs (default 5). Warn if drop > threshold_pct.
 - Skill extraction rate drop: same pattern for skills_per_job metric.

History file: JSONL produced via append_history with per-run summary including:
  avg_score, skills_per_job, jobs_processed, timestamp_utc

Outputs list of warning strings. Silent (empty list) if insufficient data.
"""
from __future__ import annotations
from pathlib import Path
import json, statistics
from typing import List

def load_history(path: Path, max_lines: int = 50):
    if not path.exists():
        return []
    lines = path.read_text(encoding='utf-8').strip().splitlines()
    out = []
    for l in lines[-max_lines:]:
        try:
            out.append(json.loads(l))
        except Exception:
            continue
    return out

def detect_anomalies(history_path: Path, recent_n: int = 5, drop_threshold_pct: float = 0.35) -> List[str]:
    hist = load_history(history_path)
    if len(hist) < recent_n + 1:
        return []  # need baseline + current
    current = hist[-1]
    prev = hist[-(recent_n+1):-1]
    warnings: List[str] = []
    def pct_drop(cur, baseline):
        if baseline <= 0:
            return 0.0
        return (baseline - cur) / baseline
    # Average score
    if 'avg_score' in current:
        prev_scores = [h.get('avg_score') for h in prev if h.get('avg_score') is not None]
        if len(prev_scores) >= recent_n:
            baseline = statistics.mean(prev_scores)
            if baseline > 0 and current.get('avg_score') is not None:
                drop = pct_drop(current['avg_score'], baseline)
                if drop > drop_threshold_pct:
                    warnings.append(f"Average score drop {drop:.0%} (current {current['avg_score']:.3f} vs baseline {baseline:.3f})")
    # Skill extraction rate
    if 'skills_per_job' in current:
        prev_rates = [h.get('skills_per_job') for h in prev if h.get('skills_per_job') is not None]
        if len(prev_rates) >= recent_n:
            baseline = statistics.mean(prev_rates)
            if baseline > 0 and current.get('skills_per_job') is not None:
                drop = pct_drop(current['skills_per_job'], baseline)
                if drop > drop_threshold_pct:
                    warnings.append(f"Skills per job drop {drop:.0%} (current {current['skills_per_job']:.2f} vs baseline {baseline:.2f})")
    return warnings

__all__ = ["detect_anomalies"]