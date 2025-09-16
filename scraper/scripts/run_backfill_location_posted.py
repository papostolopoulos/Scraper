from __future__ import annotations
"""Backfill location and posted_at fields using improved heuristics.
Run after updating collector helpers.
"""
from pathlib import Path
from jobminer.db import JobDB
from jobminer.collector import derive_location_from_description, parse_posted_text

def backfill():
    db = JobDB()
    jobs = db.fetch_all()
    updated = 0
    for j in jobs:
        changed = False
        if (not j.location) and j.description_raw:
            loc = derive_location_from_description(j.description_raw)
            if loc:
                j.location = loc
                changed = True
        if (not j.posted_at) and j.description_raw:
            # Some older rows may have a posted text inside description (rare). Attempt parse.
            # We look for a line starting with 'Posted' within first few lines.
            for line in j.description_raw.splitlines()[:6]:
                if 'post' in line.lower():
                    d = parse_posted_text(line)
                    if d:
                        j.posted_at = d
                        changed = True
                        break
        if changed:
            db.upsert_jobs([j])
            updated += 1
    print(f"Backfilled {updated} jobs with location/posted_at.")

if __name__ == '__main__':
    backfill()
