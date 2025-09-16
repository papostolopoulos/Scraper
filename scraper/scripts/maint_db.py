"""SQLite maintenance: VACUUM, ANALYZE, index check.

Usage (PowerShell):
  python scraper/scripts/maint_db.py --vacuum --analyze
"""
from __future__ import annotations
from pathlib import Path
import argparse, sqlite3, time

DB_PATH = Path('scraper/data/db.sqlite')

def ensure_index(conn):
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_norm_keys ON jobs(company_name_normalized, location_normalized, title)")
    except Exception:
        pass

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vacuum', action='store_true')
    ap.add_argument('--analyze', action='store_true')
    args = ap.parse_args()
    if not DB_PATH.exists():
        print('DB not found:', DB_PATH)
        return
    with sqlite3.connect(DB_PATH) as conn:
        ensure_index(conn)
        if args.vacuum:
            t0 = time.time()
            conn.execute('VACUUM')
            print('VACUUM done in', round(time.time()-t0,2),'s')
        if args.analyze:
            t1 = time.time()
            conn.execute('ANALYZE')
            print('ANALYZE done in', round(time.time()-t1,2),'s')
    print('Maintenance complete.')

if __name__ == '__main__':
    main()