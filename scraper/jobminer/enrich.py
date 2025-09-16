"""Lightweight enrichment utilities for company normalization and location parsing.

Design goals:
- Pure-python; no heavy geo libs. Simple pattern + small map.
- Idempotent: safe to re-run on already enriched jobs.
- Extensible: can later plug real geocoder.
"""
from __future__ import annotations
import re, json
from pathlib import Path
from typing import Dict, Iterable, Tuple
from datetime import datetime, timezone
from .models import JobPosting

CANONICAL_SUFFIXES = [r",?\s*Inc\.?$", r",?\s*Inc\.?$", r",?\s*LLC$", r",?\s*Ltd\.?$", r",?\s*Limited$", r",?\s*Corporation$", r",?\s*Corp\.?$", r",?\s*GmbH$", r",?\s*SA$", r",?\s*SAS$", r",?\s*BV$", r",?\s*PLC$"]
SUFFIX_RE = re.compile("|".join(CANONICAL_SUFFIXES), re.IGNORECASE)
MULTISPACE = re.compile(r"\s+")

CITY_STATE_COUNTRY_RE = re.compile(r"^(?P<city>[A-Za-z .'-]+),?\s*(?P<region>[A-Za-z .'-]{2,})?,?\s*(?P<country>[A-Za-z .'-]{2,})?$")

COUNTRY_NORMALIZATION = {
    'United States': 'USA', 'United States of America': 'USA', 'US': 'USA', 'U.S.': 'USA', 'U.S.A.': 'USA',
    'UK': 'United Kingdom', 'U.K.': 'United Kingdom'
}

STATE_ABBR = {
    'CA': 'California', 'NY': 'New York', 'TX': 'Texas', 'WA': 'Washington', 'MA': 'Massachusetts', 'IL': 'Illinois', 'CO': 'Colorado'
}

def load_company_map(path: Path | None) -> Dict[str,str]:
    if not path or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8')) if path.suffix == '.json' else None
        if data is None:
            # Assume YAML if not json
            import yaml
            y = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
            # Accept either list of mappings or dict
            if isinstance(y, dict):
                return {k.lower(): v for k,v in y.items()}
            elif isinstance(y, list):
                out = {}
                for item in y:
                    if isinstance(item, dict):
                        for k,v in item.items():
                            out[k.lower()] = v
                return out
            return {}
        return {k.lower(): v for k,v in data.items()}
    except Exception:
        return {}

COMMON_COMPANY_CLEANUPS = [
    (re.compile(r"^(the)\s+", re.IGNORECASE), ""),
]

NORMALIZATION_VERSION = "v1.1"

_GEO_CACHE: Dict[str, Tuple[float,float]] = {}

def normalize_company(name: str, mapping: Dict[str,str]) -> str:
    raw = name.strip()
    lowered = raw.lower()
    if lowered in mapping:
        return mapping[lowered]
    # remove suffixes
    base = SUFFIX_RE.sub("", raw)
    # cleanup patterns
    for regex, repl in COMMON_COMPANY_CLEANUPS:
        base = regex.sub(repl, base)
    base = MULTISPACE.sub(" ", base).strip()
    # Title case but preserve internal capitalization heuristically
    if base.isupper() or base.islower():
        base = base.title()
    return base


def parse_location(loc: str) -> tuple[str | None, dict | None]:
    if not loc:
        return None, None
    s = loc.strip()
    # Quick remote indicators
    if re.search(r"remote", s, re.IGNORECASE):
        return "Remote", {"raw": loc, "mode_hint": "remote"}
    m = CITY_STATE_COUNTRY_RE.match(s)
    meta = {"raw": loc}
    if not m:
        return s, meta
    city = m.group('city')
    region = m.group('region')
    country = m.group('country')
    # Normalize country
    if country:
        country_clean = COUNTRY_NORMALIZATION.get(country.strip(), country.strip())
    else:
        country_clean = None
    # Expand region if looks like state abbr
    if region and region.upper() in STATE_ABBR:
        region_full = STATE_ABBR[region.upper()]
    else:
        region_full = region
    parts = [p for p in [city, region_full, country_clean] if p]
    canonical = ", ".join(parts)
    meta.update({
        'city': city,
        'region': region_full,
        'country': country_clean,
        'source': 'regex_v1'
    })
    return canonical, meta


def geocode_location(canonical: str) -> tuple[float | None, float | None]:
    """Very naive geocode stub using small hardcoded hints and cache.
    Replace with real provider (e.g., Nominatim) externally.
    """
    if not canonical:
        return None, None
    if canonical in _GEO_CACHE:
        return _GEO_CACHE[canonical]
    # Tiny heuristic dictionary (expand later)
    hints = {
        'seattle': (47.6062, -122.3321),
        'boston': (42.3601, -71.0589),
        'new york': (40.7128, -74.0060),
        'san francisco': (37.7749, -122.4194),
        'london': (51.5074, -0.1278),
        'barcelona': (41.3851, 2.1734),
    }
    low = canonical.lower()
    for k, v in hints.items():
        if k in low:
            _GEO_CACHE[canonical] = v
            return v
    return None, None


def enrich_jobs(jobs: Iterable[JobPosting], company_map: Dict[str,str]) -> int:
    updated = 0
    for job in jobs:
        changed = False
        if job.company_name:
            if not job.company_name_normalized:
                norm = normalize_company(job.company_name, company_map)
                if norm != job.company_name:
                    job.company_name_normalized = norm
                    job.company_map_key = job.company_name.strip().lower() if job.company_name.strip().lower() in company_map else None
                    changed = True
        if job.location:
            if not job.location_normalized:
                loc_norm, meta = parse_location(job.location)
                if loc_norm:
                    job.location_normalized = loc_norm
                    job.location_meta = meta
                    changed = True
            # Geocode if canonical exists but no lat/lon
            if job.location_normalized and job.geocode_lat is None and job.geocode_lon is None:
                lat, lon = geocode_location(job.location_normalized)
                if lat is not None:
                    job.geocode_lat = lat
                    job.geocode_lon = lon
                    changed = True
        if changed:
            job.normalization_version = NORMALIZATION_VERSION
            job.enrichment_run_at = datetime.now(timezone.utc)
        if changed:
            updated += 1
    return updated

__all__ = [
    'normalize_company','parse_location','enrich_jobs','load_company_map','geocode_location'
]
