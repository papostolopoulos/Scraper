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
    return jobs


@dataclass
class LoadedSource:
    name: str
    instance: BaseJobSource


def load_sources(config: List[Dict[str, Any]]) -> List[LoadedSource]:
    loaded: List[LoadedSource] = []
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


def collect_from_sources(sources: List[LoadedSource]) -> List[JobPosting]:
    out: List[JobPosting] = []
    seen = set()
    for s in sources:
        try:
            jobs = s.instance.fetch() or []
            jobs = normalize_ids(jobs, s.name)
            for j in jobs:
                if j.job_id in seen:
                    continue
                seen.add(j.job_id)
                out.append(j)
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"Source {s.name} failed: {e}")
    return out
