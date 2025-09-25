from __future__ import annotations
"""Multi-source job collection & merge orchestration (Phase 1 + Phase 2).

Phase 1 (already shipped):
    * Optional ATS augmentation (Greenhouse / Lever) using title token overlap filtering.

Phase 2 (this module now includes):
    * Cross-source duplicate clustering + canonical selection.
    * Field backfill (description length, salary fields, posted_at earliest, apply_url conservation).
    * Provenance union + ordered provenance list with primary breadth source first when present.

Environment Variables (augmentation):
    JOBMINER_ENABLE_GREENHOUSE=1       Enable Greenhouse board fetches
    JOBMINER_ENABLE_LEVER=1            Enable Lever board fetches
    JOBMINER_GH_SLUGS="slug1,slug2"    Comma-separated Greenhouse company slugs
    JOBMINER_LEVER_SLUGS="s1,s2"       Comma-separated Lever company slugs
    JOBMINER_ATS_TITLE_OVERLAP=0.35    Min token overlap ratio to accept ATS posting
    JOBMINER_MAX_ATS_PER_SLUG=50       Cap per-slug postings considered

Environment Variables (Phase 2 merging):
    JOBMINER_ENABLE_PHASE2_MERGE=1     Toggle Phase 2 dedupe + field backfill (default on)
    JOBMINER_DEDUPE_PRIMARY=adzuna     Primary breadth provider name (ordering & provenance lead)
    JOBMINER_DEDUPE_ORDER_PRIMARY_FIRST=1  If set, sort merged list with primary-first

Token overlap ratio = shared(query_tokens,title_tokens)/len(query_tokens) after lowercasing &
removing short tokens (<2 chars).
"""
from typing import List, Iterable, Dict, Set
import os, re
from .models import JobPosting
from .sources.greenhouse_source import GreenhouseSource
from .sources.lever_source import LeverSource
from .sources.base import _dup_signature, _canonical_text, _merge_jobs  # type: ignore


def _tokenize(text: str) -> List[str]:
    return [t for t in re.split(r"[^A-Za-z0-9+.#]+", text.lower()) if len(t) > 1]


def _overlap_ratio(query_tokens: List[str], title: str) -> float:
    if not query_tokens:
        return 0.0
    title_tokens = set(_tokenize(title))
    if not title_tokens:
        return 0.0
    shared = sum(1 for t in query_tokens if t in title_tokens)
    return shared / len(query_tokens)


def _parse_slug_list(env_value: str | None) -> List[str]:
    if not env_value:
        return []
    return [s.strip() for s in env_value.split(',') if s.strip()]


def collect_ats_jobs(query_title: str) -> List[JobPosting]:
    enable_gh = os.getenv('JOBMINER_ENABLE_GREENHOUSE', '0').lower() in ('1','true','yes','on')
    enable_lever = os.getenv('JOBMINER_ENABLE_LEVER', '0').lower() in ('1','true','yes','on')
    if not (enable_gh or enable_lever):
        return []
    query_tokens = _tokenize(query_title)
    try:
        overlap_min = float(os.getenv('JOBMINER_ATS_TITLE_OVERLAP','0.35'))
    except Exception:
        overlap_min = 0.35
    try:
        per_slug_cap = int(os.getenv('JOBMINER_MAX_ATS_PER_SLUG','50'))
    except Exception:
        per_slug_cap = 50
    jobs: List[JobPosting] = []
    if enable_gh:
        for slug in _parse_slug_list(os.getenv('JOBMINER_GH_SLUGS')):
            src = GreenhouseSource(name=f"gh:{slug}", company_slug=slug, limit=per_slug_cap)
            for j in src.fetch():
                if _overlap_ratio(query_tokens, j.title) >= overlap_min:
                    j.provenance.append('greenhouse')
                    jobs.append(j)
    if enable_lever:
        for slug in _parse_slug_list(os.getenv('JOBMINER_LEVER_SLUGS')):
            src = LeverSource(name=f"lever:{slug}", company_slug=slug, limit=per_slug_cap)
            for j in src.fetch():
                if _overlap_ratio(query_tokens, j.title) >= overlap_min:
                    j.provenance.append('lever')
                    jobs.append(j)
    return jobs


# ------------------------- Phase 2 Merge & Enrichment -------------------------
def merge_and_enrich(jobs: List[JobPosting]) -> List[JobPosting]:
    """Cluster duplicates across sources and perform field backfill & provenance union.

    Heuristics:
      * Duplicate signature uses `_dup_signature` (apply URL host/path when non-generic; else
        company+title+location canonical text) for stable clustering.
      * Canonical job chosen preferring (a) earlier posted_at when both present, else (b)
        longer description_raw, else retain first encountered (which will usually be the
        primary breadth source).
      * Field backfill: any salary fields, posted_at, description (longer wins) already handled
        inside `_merge_jobs` which merges incoming into existing canonical.
      * Provenance: union of all sources contributing to the cluster. Ordered with primary
        source first (if present) followed by remaining sources alphabetically.
    Ordering of returned list:
      * If JOBMINER_DEDUPE_ORDER_PRIMARY_FIRST is true, primary-source-present jobs first;
        within each group preserve original encounter order.
    """
    if not jobs:
        return jobs
    primary = os.getenv("JOBMINER_DEDUPE_PRIMARY", "adzuna").strip().lower() or "adzuna"
    # Maps
    by_sig: Dict[str, JobPosting] = {}
    provenance_map: Dict[str, Set[str]] = {}
    encounter_order: List[str] = []  # signature order to preserve stable listing

    for j in jobs:
        sig = _dup_signature(j)
        if sig not in by_sig:
            by_sig[sig] = j
            encounter_order.append(sig)
        else:
            existing = by_sig[sig]
            # Decide whether to replace existing canonical with j
            replace = False
            if existing.posted_at and j.posted_at:
                if j.posted_at < existing.posted_at:
                    replace = True
            elif j.posted_at and not existing.posted_at:
                replace = True
            elif existing.posted_at and not j.posted_at:
                replace = False
            else:
                if (j.description_raw or "") and len(j.description_raw or "") > len(existing.description_raw or ""):
                    replace = True
            if replace:
                # merge existing into new canonical (carry provenance)
                _merge_jobs(j, existing)
                by_sig[sig] = j
            else:
                _merge_jobs(existing, j)
        # Track provenance contributions
        prov_list = getattr(j, "provenance", []) or []
        provenance_map.setdefault(sig, set()).update([p for p in prov_list if p])
    merged: List[JobPosting] = []
    for sig in encounter_order:
        job = by_sig[sig]
        # Final provenance union (also include any provenance created during merges)
        prov = set(job.provenance or []) | provenance_map.get(sig, set())
        # Ensure primary first if present
        ordered = []
        if primary in prov:
            ordered.append(primary)
        ordered.extend(sorted([p for p in prov if p != primary]))
        job.provenance = ordered
        merged.append(job)

    if os.getenv("JOBMINER_DEDUPE_ORDER_PRIMARY_FIRST", "1").lower() in ("1","true","yes","on"):
        merged.sort(key=lambda j: (primary not in (j.provenance or [])))  # primary-containing first
    return merged


__all__ = ['collect_ats_jobs', 'merge_and_enrich']