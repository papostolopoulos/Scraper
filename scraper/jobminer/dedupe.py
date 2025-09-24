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
from .normalization import normalize_company, normalize_title, normalize_location
import os

TITLE_CLEAN_RE = re.compile(r"[^a-z0-9]+")
_STOPWORDS = {
    'the','and','for','a','an','of','to','in','on','at','by','with','across','from','into','over','under','as','is','are'
}

def build_signature(job: JobPosting, desc_prefix: int = 0) -> str:
    # Dynamically access settings so tests that reload settings module after
    # env var changes see updated fuzzy_normalization flag without reloading this module.
    from . import settings as settings_mod  # local import to pick up reloads
    # Dynamic flag: environment variable takes precedence for test/runtime toggling.
    fuzzy_flag = os.getenv('JOBMINER_FUZZY_NORMALIZATION','0').lower() in ('1','true','yes','on')
    if not fuzzy_flag:
        # Fall back to settings object (loaded at process start)
        fuzzy_flag = getattr(settings_mod.SETTINGS, 'fuzzy_normalization', False)
    if fuzzy_flag:
        company_raw = job.company_name_normalized or job.company_name or ''
        location_raw = job.location_normalized or job.location or ''
        title_raw = job.title or ''
        company = normalize_company(company_raw)
        location = normalize_location(location_raw)
        title_clean = normalize_title(title_raw)
    else:
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
    raw = [t for t in TITLE_CLEAN_RE.sub(' ', (text or '').lower()).split() if t]
    norm: List[str] = []
    for t in raw:
        if t in _STOPWORDS:
            continue
        # Simple plural normalization: drop trailing 's' for longer words
        if len(t) > 4 and t.endswith('s'):
            t = t[:-1]
        norm.append(t)
    return norm

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
        # Always add to similarity buckets keyed by company/location
        comp = (job.company_name_normalized or job.company_name or '').lower().strip()
        loc = (job.location_normalized or job.location or '').lower().strip()
        buckets.setdefault((comp, loc), []).append(job)
        # Deterministic signature check: optionally skip when relying purely on similarity
        if enable_similarity and desc_prefix == 0:
            # Skip deterministic pass to allow similarity thresholds to govern behavior
            continue
        # Otherwise run deterministic signature pass
        sig = build_signature(job, desc_prefix=desc_prefix)
        if not sig.strip():
            continue
        first = sig_first.get(sig)
        if first is None:
            sig_first[sig] = job
            continue
        # If same signature and not already duplicate
        if job.status != 'duplicate':
            job.status = 'duplicate'
            dup_count += 1
    if not enable_similarity:
        return dup_count
    # Secondary pass: near duplicates
    # Title similarity function (use rapidfuzz if available; else fallback to difflib ratio)
    try:
        from rapidfuzz import fuzz as _rf_fuzz  # type: ignore
        def _title_score(a_t: str, b_t: str) -> int:
            return int(_rf_fuzz.partial_ratio(a_t, b_t))
    except Exception:
        import difflib as _difflib
        def _title_score(a_t: str, b_t: str) -> int:
            if a_t == b_t:
                return 100
            return int(100 * _difflib.SequenceMatcher(None, a_t, b_t).ratio())
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
                tf = _title_score((a.title or '').lower(), (b.title or '').lower())
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

__all__ = ['detect_duplicates']