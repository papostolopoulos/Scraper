import argparse
import sys
from pathlib import Path

PARENT = Path(__file__).resolve().parent.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from jobminer.db import JobDB

def cmd_list(args):
    db = JobDB()
    jobs = db.fetch_all()
    for j in jobs:
        prov = f" [prov={','.join(j.provenance)}]" if getattr(j, 'provenance', None) and args.show_provenance else ""
        print(f"{j.job_id}\t{j.score_total}\t{j.status}\t{j.company_name} - {j.title}{prov}")

def cmd_status(args):
    db = JobDB()
    db.update_status(args.job_id, args.status)
    history = db.fetch_history(args.job_id, limit=5)
    print(f"Updated {args.job_id} -> {args.status}")
    for h in history:
        print(f"  {h['changed_at']} {h['from_status']} -> {h['to_status']}")

def cmd_stats(args):
    db = JobDB()
    funnel = db.funnel_metrics()
    print("Funnel Metrics:")
    for k,v in funnel.items():
        print(f"  {k}: {v}")

def cmd_history(args):
    db = JobDB()
    hist = db.fetch_history(args.job_id, limit=args.limit)
    for h in hist:
        print(f"{h['changed_at']}\t{h['from_status']}\t{h['to_status']}")

if __name__ == '__main__':
    ap = argparse.ArgumentParser("job cli")
    sub = ap.add_subparsers(dest='cmd', required=True)

    lp = sub.add_parser('list')
    lp.add_argument('--show-provenance', action='store_true', help='Show merged provenance sources for each job')
    lp.set_defaults(func=cmd_list)

    sp = sub.add_parser('status')
    sp.add_argument('job_id')
    sp.add_argument('status', choices=['new','reviewed','shortlisted','applied','archived'])
    sp.set_defaults(func=cmd_status)

    stp = sub.add_parser('stats')
    stp.set_defaults(func=cmd_stats)

    hp = sub.add_parser('history')
    hp.add_argument('job_id')
    hp.add_argument('--limit', type=int, default=20)
    hp.set_defaults(func=cmd_history)

    args = ap.parse_args()
    args.func(args)
