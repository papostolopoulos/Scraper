"""Heuristic duplicate + near-duplicate detection for job postings.

Primary deterministic signature pass (fast O(n)):
    1. Signature = normalized company | normalized location | cleaned title | optional desc prefix.
    2. First job per signature kept; later ones marked duplicate.

Secondary similarity pass (optional) to catch near-duplicates with small textual deltas:
    - For jobs sharing company + location + (fuzzy title >= title_fuzzy_min) compute:
                * Jaccard of token sets from (lowercased description_clean)
                * Optional prefix similarity if desc_prefix>0
    - If Jaccard >= jaccard_min (default 0.82) AND title fuzz >= title_fuzzy_min (default 90), mark the newer as duplicate.

Constraints:
    - Avoid O(n^2) blow-up by bucketing candidates by (company, location) first.
    - Keep function signature backward compatible; new thresholds arguments exposed.
"""
from __future__ import annotations
from typing import Iterable, Dict, List, Tuple
from datetime import datetime, timezone
import re
from .models import JobPosting

TITLE_CLEAN_RE = re.compile(r"[^a-z0-9]+")

def build_signature(job: JobPosting, desc_prefix: int = 0) -> str:
    company = (job.company_name_normalized or job.company_name or '').lower().strip()
    location = (job.location_normalized or job.location or '').lower().strip()
    title = (job.title or '').lower().strip()
    title_clean = TITLE_CLEAN_RE.sub(' ', title).strip()
    parts = [company, location, title_clean]
    if desc_prefix and job.description_clean:
        snippet = job.description_clean[:desc_prefix].lower()
        parts.append(snippet)
    return "|".join(parts)

def _tokenize(text: str) -> List[str]:
    return [t for t in TITLE_CLEAN_RE.sub(' ', (text or '').lower()).split() if t]

def _jaccard(a: List[str], b: List[str]) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    if inter == 0:
        return 0.0
    return inter / len(sa | sb)

def detect_duplicates(
    jobs: Iterable[JobPosting],
    desc_prefix: int = 120,
    enable_similarity: bool = True,
    jaccard_min: float = 0.82,
    title_fuzzy_min: int = 90,
) -> int:
    """Return number of jobs newly marked as duplicate.

    Parameters
    ----------
    desc_prefix: int
        If >0 include leading description chars in deterministic signature.
    enable_similarity: bool
        Enable secondary near-duplicate detection via Jaccard + fuzzy title.
    jaccard_min: float
        Minimum Jaccard token similarity for near-duplicate.
    title_fuzzy_min: int
        Minimum rapidfuzz partial_ratio score to treat titles as similar.
    """
    sig_first: Dict[str, JobPosting] = {}
    dup_count = 0
    # Sort by collected_at ascending so earliest kept
    def _ts(j):
        dt = j.collected_at
        if dt is None:
            return 0
        # Normalize to naive UTC timestamp for ordering to avoid aware/naive compare
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.timestamp()
    jobs_sorted = sorted(jobs, key=_ts)
    # Collect buckets for optional similarity pass
    buckets: Dict[Tuple[str,str], List[JobPosting]] = {}
    for job in jobs_sorted:
        sig = build_signature(job, desc_prefix=desc_prefix)
        if not sig.strip():
            continue
        first = sig_first.get(sig)
        if first is None:
            sig_first[sig] = job
            # bucket key without title/desc to allow near duplicate within company/location
            comp = (job.company_name_normalized or job.company_name or '').lower().strip()
            loc = (job.location_normalized or job.location or '').lower().strip()
            buckets.setdefault((comp, loc), []).append(job)
            continue
        # If same signature and not already duplicate
        if job.status != 'duplicate':
            job.status = 'duplicate'
            dup_count += 1
    if not enable_similarity:
        return dup_count
    # Secondary pass: near duplicates
    try:
        from rapidfuzz import fuzz
    except ImportError:
        return dup_count  # silently skip
    for (comp, loc), bucket in buckets.items():
        if len(bucket) < 2:
            continue
        # Compare each with canonical earliest (first in time already) and others with each other if not already duplicate
        for i in range(len(bucket)):
            a = bucket[i]
            if a.status == 'duplicate':
                continue
            tokens_a = _tokenize(a.description_clean or '')
            for j in range(i+1, len(bucket)):
                b = bucket[j]
                if b.status == 'duplicate':
                    continue
                # Title fuzzy
                tf = fuzz.partial_ratio((a.title or '').lower(), (b.title or '').lower())
                if tf < title_fuzzy_min:
                    continue
                jac = _jaccard(tokens_a, _tokenize(b.description_clean or ''))
                if jac >= jaccard_min:
                    # Mark later (by collected_at) as duplicate
                    later = b if b.collected_at >= a.collected_at else a
                    if later.status != 'duplicate':
                        later.status = 'duplicate'
                        dup_count += 1
    return dup_count
    return dup_count

__all__ = ['detect_duplicates']