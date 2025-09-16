import argparse
import yaml
from pathlib import Path
import logging

from jobminer.db import JobDB
from jobminer.sources.base import load_sources, collect_from_sources
from jobminer.logging_config import setup_logging, log_event

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Multi-source ingestion runner")
    ap.add_argument("--config", default="config/sources.yml", help="Path to sources.yml")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()
    setup_logging(debug=args.debug)
    logger = logging.getLogger("ingest")

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        raise SystemExit(f"Sources config not found: {cfg_path}")
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    src_entries = cfg.get("sources", [])
    loaded = load_sources(src_entries)
    jobs = collect_from_sources(loaded)
    db = JobDB()
    before = {j.job_id for j in db.fetch_all()}
    if jobs:
        db.upsert_jobs(jobs)
    after = {j.job_id for j in db.fetch_all()}
    inserted = len(after - before)
    logger.info(f"Ingestion complete sources={len(loaded)} jobs_collected={len(jobs)} new_jobs={inserted}")
    log_event("ingest_complete", sources=len(loaded), collected=len(jobs), new=inserted)
