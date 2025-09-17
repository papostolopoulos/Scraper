from __future__ import annotations
"""Daily snapshot script.

Computes a small set of metrics from the current DB (optionally runs scoring first),
writes a dated JSON snapshot and appends to a JSONL history.

Usage (PowerShell):
  # compute snapshot only (no scoring)
  python scraper/scripts/daily_snapshot.py

  # run a quick scoring pass first (uses existing resume/seed defaults)
  python scraper/scripts/daily_snapshot.py --score-first

Outputs:
  - scraper/data/daily_snapshots/YYYY-MM-DD.json
  - scraper/data/daily_snapshots/history.jsonl (append-only)
"""
import argparse, json
from pathlib import Path
from datetime import datetime, timezone

from scraper.jobminer.db import JobDB
from scraper.jobminer.settings import SETTINGS


def compute_snapshot(db: JobDB) -> dict:
    jobs = db.fetch_all()
    n = len(jobs)
    titles = [j.title for j in jobs if j.title]
    top_titles = []
    try:
        from collections import Counter
        top_titles = [t for t,_ in Counter(titles).most_common(5)]
    except Exception:
        pass
    scores = [j.score_total for j in jobs if j.score_total is not None]
    skills_counts = [len(j.skills_extracted) for j in jobs if j.skills_extracted]
    avg_score = round(sum(scores)/len(scores), 4) if scores else None
    skills_per_job = round(sum(skills_counts)/len(skills_counts), 2) if skills_counts else None
    snapshot = {
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'jobs_total': n,
        'avg_score': avg_score,
        'skills_per_job': skills_per_job,
        'top_titles': top_titles,
    }
    # Include last run timings if present
    try:
        run_summary = json.loads(SETTINGS.metrics_output_path.read_text(encoding='utf-8'))
        if isinstance(run_summary, dict):
            snapshot['last_run'] = {
                'timings': run_summary.get('timings') or run_summary.get('timing') or {},
                'score_distribution': run_summary.get('score_distribution'),
                'skill_cache_hits': run_summary.get('skill_cache_hits'),
                'skill_cache_misses': run_summary.get('skill_cache_misses'),
            }
    except Exception:
        pass
    return snapshot


def append_history(rec: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')


def main():
    ap = argparse.ArgumentParser(description='Compute a daily snapshot of key metrics.')
    ap.add_argument('--score-first', action='store_true', help='Run a quick scoring pass before snapshot')
    ap.add_argument('--resume', default='Resume - Paris_Apostolopoulos.pdf')
    ap.add_argument('--seed', default='config/seed_skills.txt')
    ap.add_argument('--max-workers', type=int, default=None, help='Override worker count for quick scoring')
    args = ap.parse_args()

    db = JobDB()

    if args.score_first:
        from scraper.jobminer.pipeline import score_all
        base = Path(__file__).resolve().parent.parent
        resume_pdf = base.parent / args.resume
        seed_skills = base / args.seed
        # graceful resume fallback
        if not resume_pdf.exists():
            dummy = base / 'data' / 'dummy.pdf'
            dummy.parent.mkdir(parents=True, exist_ok=True)
            dummy.write_bytes(b"%PDF-1.3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF")
            resume_pdf = dummy
        score_all(db, resume_pdf, seed_skills, write_summary=True, max_workers=args.max_workers)

    snapshot = compute_snapshot(db)
    out_dir = Path('scraper/data/daily_snapshots')
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    json_path = out_dir / f'{date_str}.json'
    json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
    append_history(snapshot, out_dir / 'history.jsonl')
    print(f'Wrote daily snapshot to {json_path}')


if __name__ == '__main__':
    main()
