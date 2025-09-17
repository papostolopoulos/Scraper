from __future__ import annotations
"""Weekly summary from daily snapshots.

Reads daily snapshot JSONL and produces a concise weekly Markdown summary.

Usage (PowerShell):
  python scraper/scripts/weekly_summary.py                         # default 7 days
  python scraper/scripts/weekly_summary.py --days 14 --json        # print JSON summary for last 14 days
  python scraper/scripts/weekly_summary.py --history path\to.jsonl --out out.md
"""
import argparse
import json
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any


def load_history(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with path.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    # skip malformed
                    pass
    except Exception:
        return []
    return rows


essential_keys = ['timestamp_utc','jobs_total','avg_score','skills_per_job','top_titles']


def filter_last_days(rows: List[Dict[str, Any]], days: int) -> List[Dict[str, Any]]:
    if not rows or days is None:
        return rows
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out: List[Dict[str, Any]] = []
    for r in rows:
        ts = r.get('timestamp_utc')
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts)
        except Exception:
            # try strip Z
            try:
                dt = datetime.fromisoformat(ts.replace('Z','+00:00'))
            except Exception:
                continue
        if dt >= cutoff:
            out.append(r)
    return out


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {
            'runs': 0,
            'date_span': None,
            'avg_jobs_total': 0,
            'avg_score': None,
            'avg_skills_per_job': None,
            'top_titles': [],
        }
    jobs = [r.get('jobs_total', 0) for r in rows]
    scores = [r.get('avg_score') for r in rows if r.get('avg_score') is not None]
    skills_rates = [r.get('skills_per_job') for r in rows if r.get('skills_per_job') is not None]
    # Aggregate top titles
    title_counter: Counter[str] = Counter()
    for r in rows:
        for t in (r.get('top_titles') or []):
            title_counter[t] += 1
    # Date span
    try:
        first_ts = rows[0].get('timestamp_utc')
        last_ts = rows[-1].get('timestamp_utc')
    except Exception:
        first_ts = last_ts = None
    return {
        'runs': len(rows),
        'date_span': (first_ts, last_ts),
        'avg_jobs_total': round(sum(jobs)/len(jobs), 1) if jobs else 0,
        'avg_score': round(sum(scores)/len(scores), 4) if scores else None,
        'avg_skills_per_job': round(sum(skills_rates)/len(skills_rates), 2) if skills_rates else None,
        'top_titles': title_counter.most_common(5),
    }


def render_markdown(summary: Dict[str, Any]) -> str:
    if not summary or summary.get('runs', 0) == 0:
        return "# Weekly Summary\n\nNo data available for the selected period.\n"
    lines = []
    lines.append('# Weekly Summary')
    span = summary.get('date_span')
    if span and isinstance(span, (list, tuple)):
        lines.append(f"Period: {span[0]} → {span[1]}")
    lines.append('')
    lines.append('Key metrics:')
    lines.append(f"- Runs: {summary.get('runs')}")
    lines.append(f"- Avg jobs total: {summary.get('avg_jobs_total')}")
    if summary.get('avg_score') is not None:
        lines.append(f"- Avg score mean: {summary.get('avg_score')}")
    if summary.get('avg_skills_per_job') is not None:
        lines.append(f"- Avg skills per job: {summary.get('avg_skills_per_job')}")
    top = summary.get('top_titles') or []
    if top:
        lines.append('')
        lines.append('Top titles:')
        for title, count in top:
            lines.append(f"- {title} ({count})")
    lines.append('')
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description='Summarize daily snapshot history into a weekly Markdown report.')
    ap.add_argument('--history', default='scraper/data/daily_snapshots/history.jsonl')
    ap.add_argument('--days', type=int, default=7, help='Number of days to include (approx by timestamp)')
    ap.add_argument('--out', default='scraper/data/daily_snapshots/weekly_summary.md')
    ap.add_argument('--json', action='store_true', help='Print JSON summary to stdout instead of writing Markdown file')
    args = ap.parse_args()

    rows = load_history(Path(args.history))
    rows = filter_last_days(rows, args.days)
    summary = summarize(rows)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    md = render_markdown(summary)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding='utf-8')
    print(f'Wrote weekly summary to {out_path}')


if __name__ == '__main__':
    main()
