"""Summarize pipeline run history JSONL.

Usage (PowerShell):
  python scraper/scripts/summarize_history.py --history pipeline_history.jsonl --last 30

Outputs aggregate stats: runs, date span, avg collected, avg new, avg score mean, p90 total score, coverage trends.
"""
from __future__ import annotations
from pathlib import Path
import json, argparse, statistics as stats, datetime as dt

def load_history(path: Path, last: int | None):
    if not path.exists():
        return []
    rows = []
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    if last:
        rows = rows[-last:]
    return rows

def summarize(rows):
    if not rows:
        return {}
    collected = [r.get('collected_total',0) for r in rows]
    new = [r.get('new_total',0) for r in rows]
    score_means = [r.get('score_distribution',{}).get('mean') for r in rows if r.get('score_distribution',{}).get('mean') is not None]
    # coverage time series
    coverage_series = {}
    for r in rows:
        fc = r.get('field_coverage') or {}
        for k,v in fc.items():
            coverage_series.setdefault(k, []).append(v)
    span = None
    try:
        first_ts = rows[0].get('timestamp_utc')
        last_ts = rows[-1].get('timestamp_utc')
        if first_ts and last_ts:
            span = (first_ts, last_ts)
    except Exception:
        pass
    out = {
        'runs': len(rows),
        'date_span': span,
        'avg_collected': round(stats.mean(collected),2) if collected else 0,
        'avg_new': round(stats.mean(new),2) if new else 0,
        'avg_score_mean': round(stats.mean(score_means),4) if score_means else None,
        'coverage_latest': {k:v_list[-1] for k,v_list in coverage_series.items()},
        'coverage_trend_delta': {k: round(v_list[-1]-v_list[0],1) for k,v_list in coverage_series.items() if len(v_list)>1},
    }
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--history', default='scraper/data/exports/pipeline_history.jsonl')
    ap.add_argument('--last', type=int, help='Only include last N runs')
    ap.add_argument('--json', action='store_true', help='Print raw JSON summary')
    args = ap.parse_args()
    rows = load_history(Path(args.history), args.last)
    summary = summarize(rows)
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return
    if not summary:
        print('No history data.')
        return
    print(f"Runs: {summary['runs']} span: {summary.get('date_span')}")
    print(f"Avg collected: {summary['avg_collected']} | Avg new: {summary['avg_new']} | Avg score mean: {summary['avg_score_mean']}")
    print('Coverage latest:', summary['coverage_latest'])
    if summary.get('coverage_trend_delta'):
        print('Coverage delta:', summary['coverage_trend_delta'])

if __name__ == '__main__':
    main()