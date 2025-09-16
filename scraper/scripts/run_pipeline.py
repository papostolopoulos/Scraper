"""End-to-end pipeline: collect -> score -> export.

Usage examples (PowerShell):
  python scraper/scripts/run_pipeline.py --keywords "Manager" --location "San Francisco Bay Area" --limit 40
  python scraper/scripts/run_pipeline.py --use-config --headless --score --export

Flags:
  --use-config      Use searches.yml (default if no ad-hoc keywords)
  --keywords/--location/--geo-id for ad-hoc single search
  --limit           Override limit
  --headless        Headless browser
  --abort-if-login  Abort if login page encountered
  --no-score        Skip scoring step
  --no-export       Skip export step
  --resume          Resume PDF path override
  --seed            Seed skills file override
  --no-semantic     Disable semantic layer (passes through to run_score logic)
  --dry-run         Build search set and exit (no browser)
"""
from __future__ import annotations
from pathlib import Path
import sys, argparse, yaml, time, os, json

PARENT = Path(__file__).resolve().parent.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from jobminer.db import JobDB
from jobminer.collector import collect_jobs
from jobminer.logging_config import setup_logging, log_event
from jobminer.enrich import enrich_jobs, load_company_map
from jobminer.dedupe import detect_duplicates

def load_searches(base: Path, args) -> list[dict]:
    if args.keywords:
        return [{
            'keywords': args.keywords,
            'location': args.location or '',
            'geoId': args.geo_id,
            'limit': args.limit or 30
        }]
    cfg = yaml.safe_load((base / 'config' / 'searches.yml').read_text(encoding='utf-8'))
    return cfg.get('searches', [])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--keywords')
    ap.add_argument('--location')
    ap.add_argument('--geo-id')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--headless', action='store_true')
    ap.add_argument('--abort-if-login', action='store_true')
    ap.add_argument('--no-score', action='store_true')
    ap.add_argument('--no-export', action='store_true')
    ap.add_argument('--resume', default='Resume - Paris_Apostolopoulos.pdf')
    ap.add_argument('--seed', default='config/seed_skills.txt')
    ap.add_argument('--no-semantic', action='store_true')
    ap.add_argument('--max-workers', type=int, default=None, help='Max worker threads for skill extraction (default 1)')
    ap.add_argument('--debug', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--skip-if-recent-hours', type=int, default=0, help='Skip collection if a job was collected within this many hours')
    ap.add_argument('--summary-json', default='pipeline_summary.json', help='Write run summary JSON into exports dir (''none'' to disable)')
    ap.add_argument('--enrich-only', action='store_true', help='Run enrichment & (optionally) scoring/export without new collection')
    ap.add_argument('--dedupe-desc-prefix', type=int, default=120, help='Chars of description used in duplicate signature (0 to disable snippet component)')
    ap.add_argument('--history-jsonl', default='pipeline_history.jsonl', help='Append run summary to this JSONL file inside exports dir ("none" to disable)')
        ap.add_argument('--redact', action='store_true', help='Enable export redaction (emails/phones/urls)')
        ap.add_argument('--stream-export', action='store_true', help='Enable streaming export mode (skip Excel)')
    ap.add_argument('--allow-automation', action='store_true', help='Explicitly allow automated collection (ToS compliance gate)')
    args = ap.parse_args()

    setup_logging(debug=args.debug)
    base = PARENT
    searches = load_searches(base, args)
    if not searches:
        print('No searches configured or provided.')
        return
    if args.dry_run:
        print(f"Dry run: would execute {len(searches)} searches")
        for s in searches:
            print('  -', s)
        return
    duplicates_marked = 0
    per_search_stats = []  # ensure defined for enrich-only path
    if args.enrich_only:
        db = JobDB()
        # Perform enrichment then optionally scoring/export below
        jobs_all = db.fetch_all()
        from jobminer.enrich import enrich_jobs, load_company_map
        company_map_path = base / 'config' / 'company_map.yml'
        cmap = load_company_map(company_map_path if company_map_path.exists() else None)
        enriched = enrich_jobs(jobs_all, cmap)
        if enriched:
            db.upsert_jobs(jobs_all)
            log_event('pipeline_enrichment', enriched=enriched)
            print(f"Enriched {enriched} jobs (enrich-only mode)")
        # Duplicate detection in enrich-only mode
        from jobminer.dedupe import detect_duplicates
        duplicates_marked = detect_duplicates(jobs_all, desc_prefix=args.dedupe_desc_prefix)
        if duplicates_marked:
            db.upsert_jobs(jobs_all)
            log_event('pipeline_duplicates', duplicates=duplicates_marked)
            print(f"Marked {duplicates_marked} duplicate jobs (enrich-only mode)")
        # fall through to scoring/export logic with total_new set to enriched count for gating
        total_new = enriched
        collected_total = 0
        all_new_ids = []
        goto_scoring = True
    else:
        goto_scoring = False

    db = JobDB()
    # Skip-if-recent guard
    if args.skip_if_recent_hours > 0:
        from datetime import datetime, timezone
        jobs = db.fetch_all()
        if jobs:
            latest = max(j.collected_at for j in jobs if j.collected_at)
            age_hours = (datetime.now(timezone.utc) - latest).total_seconds() / 3600.0
            if age_hours < args.skip_if_recent_hours:
                print(f"Skip: last collection {age_hours:.2f}h ago (< {args.skip_if_recent_hours}h)")
                if not args.no_score:
                    print("Proceeding to scoring/export on existing DB...")
                else:
                    return
    user_data_dir = base / 'data' / 'browser_profile'
    user_data_dir.mkdir(parents=True, exist_ok=True)

    total_new = 0
    collected_total = 0
    all_new_ids = []
    t0 = time.time()
    t_collect_start = time.time()
    force_headless_env = os.getenv('SCRAPER_FORCE_HEADLESS')
    if force_headless_env is not None:
        forced_headless = force_headless_env == '1'
    else:
        forced_headless = args.headless
    abort_flag = args.abort_if_login or os.getenv('SCRAPER_ABORT_IF_LOGIN') == '1'
    if not args.enrich_only:
        from jobminer.compliance import automation_allowed
        if not automation_allowed(base, cli_flag=args.allow_automation):
            print('Automated collection blocked: explicit opt-in required (use --allow-automation or set SCRAPER_ALLOW_AUTOMATION=1)')
            return
        for s in searches:
            limit = int(args.limit or s.get('limit', 30))
            jobs = collect_jobs(s, limit=limit, user_data_dir=user_data_dir, headless=forced_headless, abort_if_login=abort_flag)
            collected_total += len(jobs)
            if not jobs:
                continue
            existing_ids = {j.job_id for j in db.fetch_all()}
            db.upsert_jobs(jobs)
            new_ids = {j.job_id for j in db.fetch_all()} - existing_ids
            total_new += len(new_ids)
            all_new_ids.extend(list(new_ids))
            log_event('pipeline_search_complete', keywords=s.get('keywords'), collected=len(jobs), new=len(new_ids))
            per_search_stats.append({'keywords': s.get('keywords'), 'collected': len(jobs), 'new': len(new_ids), 'limit': limit})
    t_collect_end = time.time()

    if not args.enrich_only:
        log_event('pipeline_collection_complete', collected=collected_total, new=total_new, elapsed=round(time.time()-t0,2))
        print(f"Collection finished collected={collected_total} new={total_new}")

    # Enrichment (company + location normalization) for all jobs (lightweight)
    t_enrich_start = time.time()
    if not args.enrich_only:
        try:
            company_map_path = base / 'config' / 'company_map.yml'
            cmap = load_company_map(company_map_path if company_map_path.exists() else None)
            jobs_all = db.fetch_all()
            enriched = enrich_jobs(jobs_all, cmap)
            duplicates_marked = detect_duplicates(jobs_all, desc_prefix=args.dedupe_desc_prefix)
            if enriched or duplicates_marked:
                db.upsert_jobs(jobs_all)
            if enriched:
                log_event('pipeline_enrichment', enriched=enriched)
                print(f"Enriched {enriched} jobs with normalization")
            if duplicates_marked:
                log_event('pipeline_duplicates', duplicates=duplicates_marked)
                print(f"Marked {duplicates_marked} duplicate jobs")
        except Exception as e:
            print('Enrichment/Dedupe step failed:', e)
    t_enrich_end = time.time()

    # Scoring
    t_score_start = time.time()
    scored = 0
    if not args.no_score and total_new > 0:
        from jobminer.pipeline import score_all
        resume_pdf = base.parent / args.resume
        seed_skills = base / args.seed
        if not resume_pdf.exists():
            print(f"Resume not found at {resume_pdf}; skipping scoring.")
        else:
            semantic_override = False if args.no_semantic else None
            scored = score_all(db, resume_pdf, seed_skills, semantic_override=semantic_override, max_workers=args.max_workers)
            log_event('pipeline_scored', scored=scored)
            print(f"Scored {scored} jobs")
    t_score_end = time.time()

    # Export
    summary = {
        'collected_total': collected_total,
        'new_total': total_new,
        'new_job_ids': all_new_ids,
        'scored': scored,
        'export_files': [],
        'duplicates_marked': duplicates_marked,
        'per_search': per_search_stats
    }

    t_export_start = time.time()
    if not args.no_export:
        from jobminer.exporter import Exporter
    exporter = Exporter(db, base / 'data' / 'exports', stream=args.stream_export or None, redact=args.redact or None)
        paths = exporter.export_all()
        log_event('pipeline_export_complete', files=len(paths))
        print('Exported files:' if paths else 'No jobs to export')
        for p in paths:
            print('  ', p)
        summary['export_files'] = [str(p) for p in paths]
    t_export_end = time.time()

    # Summary stats (field coverage) and optional JSON output
    try:
        jobs_all = db.fetch_all()
        n = len(jobs_all)
        def coverage(attr):
            return round(100.0 * sum(1 for j in jobs_all if getattr(j, attr)) / n, 1) if n else 0.0
        field_cov = {
            'location': coverage('location'),
            'location_normalized': coverage('location_normalized'),
            'company_name_normalized': coverage('company_name_normalized'),
            'work_mode': coverage('work_mode'),
            'posted_at': coverage('posted_at'),
            'offered_salary_min': coverage('offered_salary_min'),
            'benefits': round(100.0 * sum(1 for j in jobs_all if j.benefits) / n, 1) if n else 0.0,
        }
        summary['field_coverage'] = field_cov
        print('Field coverage (%):', field_cov)
        # Score distribution stats
        scores = [j.score_total for j in jobs_all if j.score_total is not None]
        if scores:
            import statistics as stats
            summary['score_distribution'] = {
                'count': len(scores),
                'mean': round(stats.mean(scores),4),
                'median': round(stats.median(scores),4),
                'p90': round(sorted(scores)[int(0.9*len(scores))-1],4) if len(scores)>=10 else None,
                'max': round(max(scores),4),
            }
        # Timing metrics
        summary['timing'] = {
            'total_seconds': round(time.time()-t0,3),
            'collection_seconds': round((t_collect_end - t_collect_start),3) if not args.enrich_only else 0.0,
            'enrichment_seconds': round((t_enrich_end - t_enrich_start),3),
            'scoring_seconds': round((t_score_end - t_score_start),3),
            'export_seconds': round((t_export_end - t_export_start),3),
        }
    except Exception:
        pass

    if args.summary_json.lower() != 'none':
        try:
            out_dir = base / 'data' / 'exports'
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / args.summary_json).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
            print('Summary JSON written to', out_dir / args.summary_json)
        except Exception as e:
            print('Failed writing summary JSON:', e)

    # Append to history log if enabled
    if args.history_jsonl.lower() != 'none':
        from jobminer.history import append_history
        try:
            out_dir = base / 'data' / 'exports'
            append_history(summary, out_dir / args.history_jsonl)
            print('Appended run to history', out_dir / args.history_jsonl)
        except Exception as e:
            print('Failed appending history:', e)

if __name__ == '__main__':
    main()
