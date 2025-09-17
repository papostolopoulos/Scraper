from __future__ import annotations
"""Benchmark semantic enrichment overhead.

Measures extraction speed and enrichment deltas across all jobs in the DB (or a sample).

Outputs a JSON metrics file under data/benchmarks/semantic_benchmark.json with fields:
  total_jobs, sampled_jobs, heuristic_time_s, semantic_time_s, avg_skills_heuristic,
  avg_skills_semantic, avg_added_semantic, threshold, bigrams, max_new, speed_ratio.

Usage (PowerShell):
  python scraper/scripts/benchmark_semantic.py --limit 200

Environment overrides for semantic config apply as normal.
"""
import argparse
import json
import time
from pathlib import Path
from statistics import mean

from scraper.jobminer.db import JobDB
from scraper.jobminer.skills import extract_skills
from scraper.jobminer.semantic_enrich import SemanticEnricher


def benchmark(limit: int | None = None):
    db = JobDB()
    jobs = db.fetch_all()
    total = len(jobs)
    if limit and total > limit:
        jobs = jobs[:limit]
    sampled = len(jobs)
    # Gather a union of seed skills (from skills_meta base_extracted if present) else fallback to collected skills
    seed_set = []
    for j in jobs:
        sm = getattr(j, 'skills_meta', None) or {}
        base = sm.get('base_extracted') or j.skills_extracted or []
        for s in base:
            if s not in seed_set:
                seed_set.append(s)
    if not seed_set:
        # fallback minimal seed set if DB empty of skills
        seed_set = ['python','sql','etl','aws','kubernetes','pandas','spark']
    # Heuristic only pass
    h_counts = []
    t0 = time.perf_counter()
    for j in jobs:
        h = extract_skills(j.description_clean or j.description_raw or '', seed_set, semantic=False)
        h_counts.append(len(h))
    t1 = time.perf_counter()
    # Semantic pass
    s_counts = []
    t2 = time.perf_counter()
    for j in jobs:
        s = extract_skills(j.description_clean or j.description_raw or '', seed_set, semantic=True)
        s_counts.append(len(s))
    t3 = time.perf_counter()
    # Refine added counts by recomputing heuristic for each job to align lengths (avoid assuming uniform heuristic length)
    added_counts = []
    for j in jobs:
        h = extract_skills(j.description_clean or j.description_raw or '', seed_set, semantic=False)
        s = extract_skills(j.description_clean or j.description_raw or '', seed_set, semantic=True)
        base_set = set(h)
        added = [sk for sk in s if sk not in base_set]
        added_counts.append(len(added))
    enr = SemanticEnricher()
    metrics = {
        'total_jobs': total,
        'sampled_jobs': sampled,
        'heuristic_time_s': round(t1 - t0, 4),
        'semantic_time_s': round(t3 - t2, 4),
        'avg_skills_heuristic': round(mean(h_counts), 2) if h_counts else 0.0,
        'avg_skills_semantic': round(mean(s_counts), 2) if s_counts else 0.0,
        'avg_added_semantic': round(mean(added_counts), 2) if added_counts else 0.0,
        'threshold': enr.similarity_threshold,
        'bigrams': enr.enable_bigrams,
        'max_new': enr.max_new,
        'speed_ratio': round(((t3 - t2) / (t1 - t0)), 3) if (t1 - t0) > 0 else None,
    }
    out_dir = Path('scraper/data/benchmarks')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'semantic_benchmark.json'
    out_path.write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    return metrics, out_path


def main():
    ap = argparse.ArgumentParser(description='Benchmark semantic enrichment performance.')
    ap.add_argument('--limit', type=int, default=None, help='Limit number of jobs sampled')
    args = ap.parse_args()
    metrics, path = benchmark(limit=args.limit)
    print(f"Benchmark complete -> {path}\n" + json.dumps(metrics, indent=2))


if __name__ == '__main__':
    main()
