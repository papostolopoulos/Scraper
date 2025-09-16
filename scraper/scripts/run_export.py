from pathlib import Path
import sys

PARENT = Path(__file__).resolve().parent.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from jobminer.db import JobDB
from jobminer.exporter import Exporter
import argparse, os

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument('--stream', action='store_true', help='Enable streaming CSV export (skip Excel)')
    ap.add_argument('--redact', action='store_true', help='Enable redaction of text fields using config/redaction.yml patterns')
    args = ap.parse_args()
    base = Path(__file__).resolve().parent.parent
    db = JobDB()
    exporter = Exporter(db, base / 'data' / 'exports', stream=args.stream or None, redact=args.redact or None)
    paths = exporter.export_all()
    if paths:
        print(f"Exported: {paths}")
    else:
        print("No jobs in database yet.")
