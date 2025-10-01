#!/usr/bin/env python
from __future__ import annotations
"""Convenience wrapper: generate provenance diversity first, then weekly summary.

Usage (PowerShell):
  python scripts/run_weekly_report.py --days 7

Outputs:
  - snapshots/provenance_diversity.json
  - snapshots/weekly_summary.md
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> int:
    print("$", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=7)
    args = ap.parse_args()
    # 1) provenance diversity
    prov = [sys.executable, 'scripts/provenance_diversity.py', '--runs', 'snapshots/runs.jsonl', '--out', 'snapshots/provenance_diversity.json']
    rc = run(prov)
    if rc != 0:
        print('provenance_diversity failed (continuing)')
    # 2) weekly summary
    weekly = [sys.executable, 'scripts/weekly_summary.py', '--runs', 'snapshots/runs.jsonl', '--days', str(args.days), '--out', 'snapshots/weekly_summary.md']
    rc2 = run(weekly)
    return rc2


if __name__ == '__main__':
    raise SystemExit(main())
