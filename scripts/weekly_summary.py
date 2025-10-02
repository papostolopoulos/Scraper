#!/usr/bin/env python
from __future__ import annotations
"""Weekly summary generator from runs.jsonl snapshots.

This module exposes three test-friendly functions used by tests/test_weekly_summary.py:
- load_runs(path: Path, days: int | None) -> list[dict]
- summarize(runs: list[dict]) -> dict
- render(summary: dict, start: datetime, end: datetime) -> str (markdown)

It reads snapshots/runs.jsonl lines where each line is a JSON object like:
{ ts, status, count, limit, timings{fetch_sec,scoring_sec,total_sec}, merge{effectiveness}, query_title }

Usage (PowerShell):
    python scripts/weekly_summary.py --runs snapshots/runs.jsonl --days 7 --out snapshots/weekly_summary.md
    python scripts/weekly_summary.py --json  # print summary JSON
"""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import median
from typing import Any, List, Dict, Tuple


def _parse_ts(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        try:
            # tolerate Z suffix
            return datetime.fromisoformat(ts.replace('Z', '+00:00'))
        except Exception:
            return None


def _read_jsonl(path: Path, limit: int) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding='utf-8').splitlines()[-limit:]
    except Exception:
        return []
    rows: List[Dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            # tolerate bad lines
            continue
    return rows


def _map_pipeline_history_record(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Map a pipeline_history.jsonl record into the runs.jsonl schema.

    Expected input keys (best-effort):
      - timestamp_utc (str)
      - timing.total_seconds, timing.scoring_seconds (floats)
      - score_distribution.count (int) or scored/collected_total as fallback
    """
    ts = obj.get('timestamp_utc')
    timing = obj.get('timing', {}) or {}
    score_dist = obj.get('score_distribution', {}) or {}
    count = (
        score_dist.get('count')
        or obj.get('scored')
        or obj.get('collected_total')
        or 0
    )
    run: Dict[str, Any] = {
        'ts': ts,
        'status': 'done',  # history implies completed run
        'count': count,
        'limit': None,
        'timings': {
            # We may not have fine-grained fetch time; prefer available fields
            'fetch_sec': None,
            'scoring_sec': timing.get('scoring_seconds'),
            'export_sec': timing.get('export_seconds'),
            'total_sec': timing.get('total_seconds'),
        },
        'merge': {
            'effectiveness': None,
        },
        'query_title': None,
    }
    return run


def load_runs(path: Path, days: int | None = 7, limit: int = 2000) -> List[Dict[str, Any]]:
    # Primary: read the provided runs.jsonl-like file
    rows = _read_jsonl(path, limit)
    if days is None:
        primary = rows
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        primary = []
        for r in rows:
            ts = _parse_ts(r.get('ts'))
            if ts and ts >= cutoff:
                primary.append(r)

    # If no primary runs and caller likely used the default snapshots/runs.jsonl,
    # fall back to pipeline history so weekly summaries aren’t empty.
    if not primary and path.as_posix().endswith('snapshots/runs.jsonl'):
        alt = Path('scraper/data/exports/pipeline_history.jsonl')
        hist_rows = _read_jsonl(alt, limit)
        mapped: List[Dict[str, Any]] = [_map_pipeline_history_record(o) for o in hist_rows]
        if days is None:
            return mapped
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        out: List[Dict[str, Any]] = []
        for r in mapped:
            ts = _parse_ts(r.get('ts'))
            if ts and ts >= cutoff:
                out.append(r)
        return out

    return primary


def summarize(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not runs:
        return {
            'total_runs': 0,
            'success_runs': 0,
            'avg_fetch_sec': None,
            'avg_scoring_sec': None,
            'avg_total_sec': None,
            'merge_eff_min': None,
            'merge_eff_median': None,
            'merge_eff_max': None,
            'top_titles': [],
        }
    total_runs = len(runs)
    success_runs = sum(1 for r in runs if r.get('status') == 'done')
    fetch_vals = [r.get('timings', {}).get('fetch_sec') for r in runs if r.get('timings', {}).get('fetch_sec') is not None]
    scoring_vals = [r.get('timings', {}).get('scoring_sec') for r in runs if r.get('timings', {}).get('scoring_sec') is not None]
    total_vals = [r.get('timings', {}).get('total_sec') for r in runs if r.get('timings', {}).get('total_sec') is not None]
    eff_vals = [r.get('merge', {}).get('effectiveness') for r in runs if r.get('merge', {}).get('effectiveness') is not None]
    def _avg(v: List[float]) -> float | None:
        return round(sum(v)/len(v), 3) if v else None
    eff_min = min(eff_vals) if eff_vals else None
    eff_max = max(eff_vals) if eff_vals else None
    eff_med = median(eff_vals) if eff_vals else None
    titles: Counter[str] = Counter()
    for r in runs:
        t = r.get('query_title')
        if t:
            titles[str(t).lower()] += 1
    top_titles: List[Tuple[str, int]] = titles.most_common(5)
    return {
        'total_runs': total_runs,
        'success_runs': success_runs,
        'avg_fetch_sec': _avg(fetch_vals),
        'avg_scoring_sec': _avg(scoring_vals),
        'avg_total_sec': _avg(total_vals),
        'merge_eff_min': eff_min,
        'merge_eff_median': eff_med,
        'merge_eff_max': eff_max,
        'top_titles': top_titles,
    }


def render(summary: Dict[str, Any], start: datetime | None, end: datetime | None) -> str:
    if not summary or summary.get('total_runs', 0) == 0:
        return "# Weekly Summary\n\nNo runs in the selected period.\n"
    lines: List[str] = []
    lines.append('# Weekly Summary')
    if start and end:
        lines.append(f"Period: {start.isoformat()} → {end.isoformat()}")
    lines.append('')
    lines.append(f"Runs: {summary.get('total_runs')} (success: {summary.get('success_runs')})")
    if summary.get('avg_fetch_sec') is not None:
        lines.append(f"Avg fetch: {summary.get('avg_fetch_sec')}s; Avg scoring: {summary.get('avg_scoring_sec')}s; Avg total: {summary.get('avg_total_sec')}s")
    if summary.get('merge_eff_median') is not None:
        lines.append(f"Merge effectiveness (min/med/max): {summary.get('merge_eff_min')} / {summary.get('merge_eff_median')} / {summary.get('merge_eff_max')}")
    top = summary.get('top_titles') or []
    if top:
        lines.append('')
        lines.append('Top titles:')
        for title, count in top:
            lines.append(f"- {title} ({count})")
    # Optional: include provenance diversity snapshot if present
    prov_path = Path('snapshots/provenance_diversity.json')
    try:
        if prov_path.exists():
            prov = json.loads(prov_path.read_text(encoding='utf-8'))
            lines.append('')
            lines.append('Provenance Diversity:')
            med = prov.get('median_provenance_count')
            if med is not None:
                lines.append(f"- Median sources per job: {med}")
            buckets = prov.get('buckets') or {}
            if buckets:
                # sort natural order 1,2,3,4+
                order = ['1','2','3','4+']
                parts = [f"{k}:{buckets.get(k) if isinstance(buckets, dict) else buckets.get(int(k), 0)}" for k in order]
                lines.append(f"- Distribution: {' | '.join(parts)}")
    except Exception:
        pass
    lines.append('')
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description='Generate weekly summary markdown from runs.jsonl snapshots.')
    ap.add_argument('--runs', default='snapshots/runs.jsonl')
    ap.add_argument('--days', type=int, default=7)
    ap.add_argument('--out', default='snapshots/weekly_summary.md')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    runs = load_runs(Path(args.runs), days=args.days)
    summary = summarize(runs)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=args.days)
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0
    md = render(summary, start=start, end=now)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding='utf-8')
    print(f"Wrote weekly summary to {out_path}")
    return 0


if __name__ == '__main__':
    import sys
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
