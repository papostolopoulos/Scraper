from pathlib import Path
import sys
import yaml
import argparse
import logging

# Ensure parent (scraper root) is on path when executing this file directly
PARENT = Path(__file__).resolve().parent.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from jobminer.db import JobDB
from jobminer.collector import collect_jobs
from jobminer.models import JobPosting
from jobminer.logging_config import setup_logging, log_event

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--debug', action='store_true', help='Enable debug logging')
    ap.add_argument('--limit', type=int, help='Override per-search limit (applies to all searches this run)')
    ap.add_argument('--keywords', type=str, help='Ad-hoc keywords (bypass searches.yml)')
    ap.add_argument('--location', type=str, help='Ad-hoc location')
    ap.add_argument('--geo-id', type=str, help='Ad-hoc geoId')
    ap.add_argument('--headless', action='store_true', help='Run browser headless for ad-hoc run')
    ap.add_argument('--abort-if-login', action='store_true', help='Abort immediately if login screen appears (non-interactive env)')
    args = ap.parse_args()
    setup_logging(debug=args.debug)
    logger = logging.getLogger('collector')
    base = Path(__file__).resolve().parent.parent
    cfg = yaml.safe_load((base / 'config' / 'searches.yml').read_text(encoding='utf-8'))
    searches = cfg.get('searches', [])
    # Ad-hoc override if --keywords provided
    if args.keywords:
        searches = [{
            'keywords': args.keywords,
            'location': args.location or '',
            'geoId': args.geo_id,
            'limit': args.limit or 10
        }]
        logger.info('Using ad-hoc search override')
    logger.info(f"Loaded {len(searches)} searches")
    db = JobDB()

    user_data_dir = base / 'data' / 'browser_profile'
    user_data_dir.mkdir(parents=True, exist_ok=True)

    total_new = 0
    for s in searches:
        limit = int(args.limit or s.get('limit', 30))
        jobs = collect_jobs(s, limit=limit, user_data_dir=user_data_dir, headless=args.headless, abort_if_login=args.abort_if_login)
        if not jobs:
            continue
        before = {j.job_id for j in db.fetch_all()}
        db.upsert_jobs(jobs)
        after = {j.job_id for j in db.fetch_all()}
        inserted = len(after - before)
        total_new += inserted
        logger.info(f"Search '{s.get('keywords')}' inserted={inserted} total_collected_session={len(jobs)}")
        log_event('search_persisted', keywords=s.get('keywords'), inserted=inserted, session=len(jobs))
    logger.info(f"Run complete new_jobs={total_new}")
    log_event('run_complete', new_jobs=total_new)
