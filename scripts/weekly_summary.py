#!/usr/bin/env python
"""Generate a weekly summary markdown from snapshot runs.jsonl.

Outputs file: snapshots/weekly/YYYY-WW.md containing:
- Week range (UTC)
- Total runs, successful, errors, zero-result runs
- Average timings (fetch, scoring, export, total)
- Merge effectiveness (median, avg, latest, min, max)
- Top 5 query titles by frequency
- Anomalies counts (by type)
- Table of last N (<=20) runs (timestamp, count, limit, fetch_sec, effectiveness, status)

Usage:
  python scripts/weekly_summary.py [--days 7] [--out snapshots/weekly]

Exit code 0 on success, 1 on failure (with brief message).
"""
from __future__ import annotations
import argparse, sys, json, statistics, datetime as dt
from pathlib import Path


def load_runs(snapshot_file: Path, days: int):
    if not snapshot_file.exists():
        return []
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    runs = []
    with snapshot_file.open('r', encoding='utf-8') as fh:
        for line in fh:
            line=line.strip()
            if not line: continue
            try:
                rec=json.loads(line)
            except Exception:
                continue
            try:
                ts = dt.datetime.fromisoformat(rec.get('ts').replace('Z','+00:00'))
            except Exception:
                continue
            if ts >= cutoff:
                runs.append(rec)
    return runs


def summarize(runs: list[dict]):
    if not runs:
        return {'empty': True}
    total = len(runs)
    errors = sum(1 for r in runs if r.get('status')=='error')
    zero = sum(1 for r in runs if (r.get('count') or 0)==0 and r.get('status')=='done')
    success = sum(1 for r in runs if r.get('status')=='done')
    fetch = [r.get('timings',{}).get('fetch_sec') for r in runs if r.get('timings',{}).get('fetch_sec') is not None]
    scoring = [r.get('timings',{}).get('scoring_sec') for r in runs if r.get('timings',{}).get('scoring_sec') is not None]
    export = [r.get('timings',{}).get('export_sec') for r in runs if r.get('timings',{}).get('export_sec') is not None]
    total_sec = [r.get('timings',{}).get('total_sec') for r in runs if r.get('timings',{}).get('total_sec') is not None]
    eff = [r.get('merge',{}).get('effectiveness') for r in runs if r.get('merge',{}).get('effectiveness') is not None]
    def avg(v): return round(sum(v)/len(v),3) if v else None
    def med(v): return round(statistics.median(v),3) if v else None
    titles = {}
    for r in runs:
        t = r.get('query_title')
        if t: titles[t]=titles.get(t,0)+1
    top_titles = sorted(titles.items(), key=lambda x:(-x[1], x[0]))[:5]
    return {
        'empty': False,
        'total_runs': total,
        'success_runs': success,
        'error_runs': errors,
        'zero_result_runs': zero,
        'avg_fetch_sec': avg(fetch),
        'avg_scoring_sec': avg(scoring),
        'avg_export_sec': avg(export),
        'avg_total_sec': avg(total_sec),
        'merge_eff_median': med(eff),
        'merge_eff_avg': avg(eff),
        'merge_eff_latest': eff[-1] if eff else None,
        'merge_eff_min': min(eff) if eff else None,
        'merge_eff_max': max(eff) if eff else None,
        'top_titles': top_titles,
        'latest_runs': runs[-20:],
    }


def render(summary: dict, week_start: dt.datetime, week_end: dt.datetime):
    if summary.get('empty'):
        return f"# Weekly Summary\n\nNo runs in range {week_start.date()} – {week_end.date()} (UTC).\n"
    lines=["# Weekly Summary", f"Range: {week_start.date()} – {week_end.date()} (UTC)", "", "## Overview"]
    lines.append(f"Runs: {summary['total_runs']} (success {summary['success_runs']}, errors {summary['error_runs']}, zero-result {summary['zero_result_runs']})")
    lines.append("## Timings (avg sec)")
    lines.append(f"Fetch: {summary['avg_fetch_sec']}  Scoring: {summary['avg_scoring_sec']}  Export: {summary['avg_export_sec']}  Total: {summary['avg_total_sec']}")
    lines.append("## Merge Effectiveness")
    lines.append(f"Median: {summary['merge_eff_median']}  Avg: {summary['merge_eff_avg']}  Latest: {summary['merge_eff_latest']}  Range: {summary['merge_eff_min']}–{summary['merge_eff_max']}")
    lines.append("## Top Query Titles")
    if summary['top_titles']:
        for t,c in summary['top_titles']:
            lines.append(f"- {t}: {c}")
    else:
        lines.append("(none)")
    lines.append("\n## Recent Runs (up to 20)")
    lines.append("| ts | status | count/limit | fetch_sec | total_sec | eff |")
    lines.append("|----|--------|------------|----------|----------|-----|")
    for r in summary['latest_runs']:
        eff = r.get('merge',{}).get('effectiveness')
        lines.append(f"| {r.get('ts')} | {r.get('status')} | {r.get('count')}/{r.get('limit')} | {r.get('timings',{}).get('fetch_sec')} | {r.get('timings',{}).get('total_sec')} | {eff} |")
    return "\n".join(lines)+"\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=7)
    ap.add_argument('--out', type=str, default='snapshots/weekly')
    ap.add_argument('--snap', type=str, default='snapshots/runs.jsonl')
    args = ap.parse_args()
    snap_path = Path(args.snap)
    runs = load_runs(snap_path, args.days)
    now = dt.datetime.now(dt.timezone.utc)
    week_start = now - dt.timedelta(days=args.days)
    summary = summarize(runs)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    iso_year, iso_week, _ = now.isocalendar()
    out_file = out_dir / f"{iso_year}-{iso_week:02d}.md"
    md = render(summary, week_start, now)
    out_file.write_text(md, encoding='utf-8')
    print(f"Wrote {out_file}")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
