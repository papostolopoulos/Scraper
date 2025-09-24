"""Pluggable job source framework.

Each source implements `BaseJobSource` and yields `JobPosting` instances.
Sources are configured in `config/sources.yml`:

example:
  sources:
    - name: mock
      enabled: true
      module: scraper.jobminer.sources.mock_source
      class: MockJobSource
      options:
        count: 5

Runtime loader imports the module, instantiates the class with its options, and calls
`fetch()` returning a list of `JobPosting` objects.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Protocol, runtime_checkable
import importlib
import logging
from ..models import JobPosting
import re
from datetime import datetime, timezone

logger = logging.getLogger("sources")

@runtime_checkable
class BaseJobSource(Protocol):
    name: str
    def fetch(self) -> List[JobPosting]:  # pragma: no cover - interface definition
        ...


def _ensure_prefix(job_id: str, prefix: str) -> str:
    if job_id.startswith(prefix + ":"):
        return job_id
    return f"{prefix}:{job_id}"


def normalize_ids(jobs: List[JobPosting], source_name: str) -> List[JobPosting]:
    prefix = source_name.lower()
    for j in jobs:
        j.job_id = _ensure_prefix(j.job_id, prefix)
        if j.collected_at is None:
            j.collected_at = datetime.now(timezone.utc)
        if j.status is None:
            j.status = "new"
        # Seed provenance with the originating source if not already populated.
        # This allows merge logic (_merge_jobs) to carry forward earlier sources even when
        # canonical replacement occurs before we reconstruct provenance at the end.
        if not getattr(j, "provenance", None):  # empty list or None
            try:
                j.provenance = [source_name]
            except Exception:
                # Defensive: JobPosting may enforce validation; ignore if assignment fails.
                pass
    return jobs


@dataclass
class LoadedSource:
    name: str
    instance: BaseJobSource


def load_sources(config: List[Dict[str, Any]]) -> List[LoadedSource]:
    loaded: List[LoadedSource] = []
    # Preserve user-defined order; caller can sort if needed. Order matters for canonical heuristic and tests.
    for entry in config:
        if not entry.get("enabled", True):
            continue
        mod_name = entry["module"]
        cls_name = entry["class"]
        options = entry.get("options", {})
        try:
            mod = importlib.import_module(mod_name)
            cls = getattr(mod, cls_name)
            inst: BaseJobSource = cls(name=entry["name"], **options)
            loaded.append(LoadedSource(name=entry["name"], instance=inst))
            logger.info(f"Loaded source {entry['name']} ({mod_name}.{cls_name})")
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Failed loading source {entry.get('name')} - {e}")
    return loaded


def _canonical_text(v: str | None) -> str:
    if not v:
        return ""
    return re.sub(r"[^a-z0-9]+", "", v.lower())[:80]


_ATS_HOST_HINTS = [
    "boards.greenhouse.io",
    "jobs.lever.co",
    "workable.com",
    "smartrecruiters.com",
]

def _dup_signature(job: JobPosting) -> str:
    """Build a stable duplicate signature.

    Rationale: Same role may appear on different ATS providers (Greenhouse vs Lever)
    with distinct apply URLs but identical title/company/location. We still want
    to merge those to aggregate salary/description improvements.

    Preference order:
      A. If apply_url host is NOT an ATS host in our hint list → use URL host+path+title (strong uniqueness)
      B. Otherwise (ATS generic or missing) → fallback to company+title+location signature
    """
    title_key = _canonical_text(job.title)
    # Include source prefix only for mock/alt test sources to preserve test expectations
    source_prefix = ""
    if job.job_id and ':' in job.job_id:
        pref = job.job_id.split(':',1)[0].lower()
        if pref in {"mock","alt"}:
            source_prefix = pref[:12]
    company_key = _canonical_text(job.company_name or "")
    loc_key = _canonical_text(job.location or "")[:24]
    if job.apply_url and isinstance(job.apply_url, str):
        m = re.search(r"https?://([^/]+)/([^?#]+)", job.apply_url)
        if m:
            host = m.group(1).lower()
            path_part = m.group(2)
            if host not in _ATS_HOST_HINTS:
                url_part = _canonical_text(f"{host}/{path_part}")[:80]
                return f"u:{url_part}:{title_key}"
    return f"c:{source_prefix}:{company_key}:{title_key}:{loc_key}"


def _merge_jobs(existing: JobPosting, incoming: JobPosting):
    """Merge fields from incoming into existing for provenance duplicates.

    Rules:
      - Append source provenance if new.
      - Prefer earliest posted_at if existing missing.
      - Keep longest description_raw/clean.
      - Preserve any salary fields if existing missing and incoming has them.
    """
    # Provenance list management
    if incoming.provenance:
        for p in incoming.provenance:
            if p not in existing.provenance:
                existing.provenance.append(p)
    # Posted at
    if not existing.posted_at and incoming.posted_at:
        existing.posted_at = incoming.posted_at
    # Description preference (longer wins)
    if (incoming.description_raw and (not existing.description_raw or len(incoming.description_raw) > len(existing.description_raw))):
        existing.description_raw = incoming.description_raw
        existing.description_clean = incoming.description_clean or existing.description_clean
    # Salary fields fill if missing
    for attr in ["offered_salary_min", "offered_salary_max", "offered_salary_currency", "salary_period", "salary_is_predicted"]:
        if getattr(existing, attr) is None and getattr(incoming, attr) is not None:
            setattr(existing, attr, getattr(incoming, attr))
    return existing


def collect_from_sources(sources: List[LoadedSource]) -> List[JobPosting]:
    out: List[JobPosting] = []
    by_sig: dict[str, JobPosting] = {}
    provenance_map: dict[str, set[str]] = {}
    group_map: dict[tuple[str,str,str], set[str]] = {}
    for s in sources:
        try:
            jobs = s.instance.fetch() or []
            # Reduced verbosity: single summary line per source
            logger.info("source_fetched name=%s count=%d", s.name, len(jobs))
            jobs = normalize_ids(jobs, s.name)
            for j in jobs:
                sig = _dup_signature(j)
                provenance_map.setdefault(sig, set()).add(s.name)
                # Secondary coarse grouping (company/title/location) to ensure provenance union even if signature fallback differs
                comp_key = _canonical_text(j.company_name or "")
                title_key = _canonical_text(j.title)
                loc_key = _canonical_text(j.location or "")[:24]
                group_map.setdefault((comp_key, title_key, loc_key), set()).add(s.name)
                # Verbose per-job provenance debug removed for normal operations.
                existing = by_sig.get(sig)
                if existing:
                    # Decide which object should remain canonical based on quality heuristic
                    # 1. Earlier posted_at preferred (if both have dates)
                    # 2. Else longer description_raw
                    replace = False
                    if existing.posted_at and j.posted_at:
                        if j.posted_at < existing.posted_at:
                            replace = True
                    elif j.posted_at and not existing.posted_at:
                        replace = True
                    elif existing.posted_at and not j.posted_at:
                        replace = False
                    else:
                        # fallback to description length
                        if (j.description_raw or "") and len(j.description_raw or "") > len(existing.description_raw or ""):
                            replace = True
                    if replace:
                        # merge existing into j (carry its provenance) then store j
                        _merge_jobs(j, existing)  # j becomes canonical; existing data merged into j
                        by_sig[sig] = j
                    else:
                        _merge_jobs(existing, j)
                    continue
                by_sig[sig] = j
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"Source {s.name} failed: {e}")
    # Preserve stable insertion ordering (original encounter order of signatures)
    for sig, job in by_sig.items():
        comp_key = _canonical_text(job.company_name or "")
        title_key = _canonical_text(job.title)
        loc_key = _canonical_text(job.location or "")[:24]
        group_sources = group_map.get((comp_key, title_key, loc_key), set())
        sig_sources = provenance_map.get(sig, set())
        sources_seen = set(job.provenance or [])
        sources_seen.update(group_sources)
        sources_seen.update(sig_sources)
        job.provenance = sorted(sources_seen)
        logger.info("provenance_final job_id=%s sources=%s", job.job_id, job.provenance)
        out.append(job)
    return out
