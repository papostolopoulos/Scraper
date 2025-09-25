#!/usr/bin/env python
"""Analyze provenance diversity from recent weekly summary or runs snapshots.

Outputs a small JSON + optional markdown summarizing distribution of provenance_count.
Looks for latest weekly summary (snapshots/weekly/*.md) OR falls back to scanning runs.jsonl lines.

Usage:
  python scripts/provenance_diversity.py [--runs snapshots/runs.jsonl] [--out snapshots/provenance_diversity.json]
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
from statistics import median

def parse_runs(path: Path, limit: int = 2000):
    if not path.exists():
        return []
    lines = path.read_text(encoding='utf-8').splitlines()[-limit:]
    runs = []
    for line in lines:
        line=line.strip()
        if not line: continue
        try:
            runs.append(json.loads(line))
        except Exception:
            continue
    return runs

def collect_provenance_counts(runs):
    counts = []
    for r in runs:
        # Expect exporter to have provenance_count in CSV only; not all snapshots store it.
        prov = r.get('provenance_count')
        if prov is None:
            # derive if merge.before/after present and saved>0? cannot reconstruct full distribution; skip
            continue
        try:
            counts.append(int(prov))
        except Exception:
            continue
    return counts

def bucketize(counts):
    buckets = {1:0,2:0,3:0,'4+':0}
    for c in counts:
        if c <= 1: buckets[1]+=1
        elif c == 2: buckets[2]+=1
        elif c == 3: buckets[3]+=1
        else: buckets['4+']+=1
    total = sum(buckets.values()) or 1
    pct = {str(k): round(v*100/total,2) for k,v in buckets.items()}
    return buckets, pct

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', default='snapshots/runs.jsonl')
    ap.add_argument('--out', default='snapshots/provenance_diversity.json')
    args = ap.parse_args()
    runs = parse_runs(Path(args.runs))
    counts = collect_provenance_counts(runs)
    buckets, pct = bucketize(counts)
    result = {
        'samples': len(counts),
        'buckets': buckets,
        'percentages': pct,
        'median_provenance_count': median(counts) if counts else None
    }
    out_path = Path(args.out); out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f'Wrote {out_path} ({result['samples']} samples)')
    return 0

if __name__ == '__main__':
    import sys
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
