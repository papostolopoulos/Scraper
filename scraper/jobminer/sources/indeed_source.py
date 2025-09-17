from __future__ import annotations
"""Indeed job source adapter.

This adapter intentionally does NOT perform live scraping to respect Terms of Service.
Instead it loads previously exported Indeed job posting JSON from a local file that the
user acquires manually (browser save, manual export, etc.). This keeps the ingestion
framework pluggable while avoiding automated interaction with third-party sites.

Config example (sources.yml):

  sources:
    - name: indeed
      enabled: true
      module: scraper.jobminer.sources.indeed_source
      class: IndeedJobSource
      options:
        path: data/sample/indeed_jobs.json
        limit: 50            # optional cap
        default_location: "Remote"  # fallback if not present

Expected JSON structure: list[object] with minimal keys. We tolerate varied field
names and attempt light normalization.
"""
from pathlib import Path
from typing import List, Any, Dict
import json
from datetime import datetime, timezone
import re

from ..models import JobPosting


class IndeedJobSource:
    def __init__(self, name: str, path: str, limit: int | None = None, default_location: str | None = None):
        self.name = name
        self.path = Path(path)
        self.limit = limit
        self.default_location = default_location

    def _load_raw(self) -> List[Dict[str, Any]]:
        if not self.path.exists():  # pragma: no cover - defensive
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "jobs" in data and isinstance(data["jobs"], list):
                return data["jobs"]
        except Exception:  # pragma: no cover - defensive
            return []
        return []

    def _normalize_company(self, raw: str | None) -> str | None:
        if not raw:
            return None
        cleaned = re.sub(r"\s+Inc\.?$", "", raw, flags=re.IGNORECASE).strip()
        return cleaned or raw

    def _to_posting(self, obj: Dict[str, Any]) -> JobPosting | None:
        job_id = (obj.get("job_id") or obj.get("id") or obj.get("jk"))
        title = obj.get("title") or obj.get("job_title")
        company = obj.get("company") or obj.get("company_name")
        desc = obj.get("description") or obj.get("snippet") or obj.get("desc")
        if not (job_id and title and company and desc):
            return None
        location = obj.get("location") or obj.get("job_location") or self.default_location
        # Attempt a posting date parse if provided (Indeed often has ISO or epoch strings)
        posted_at = None
        raw_date = obj.get("date") or obj.get("posted") or obj.get("posted_at")
        if isinstance(raw_date, str):
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%d %b %Y"):
                try:
                    dt = datetime.strptime(raw_date, fmt)
                    posted_at = dt.date()
                    break
                except ValueError:
                    continue
        elif isinstance(raw_date, (int, float)) and raw_date > 0:
            try:
                posted_at = datetime.fromtimestamp(raw_date, timezone.utc).date()
            except Exception:  # pragma: no cover
                pass

        return JobPosting(
            job_id=str(job_id),
            title=str(title).strip(),
            company_name=company.strip(),
            company_name_normalized=self._normalize_company(company),
            location=location,
            description_raw=desc,
            description_clean=desc,  # downstream cleaner can refine later
            collected_at=datetime.now(timezone.utc),
            posted_at=posted_at,
        )

    def fetch(self) -> List[JobPosting]:
        raw_jobs = self._load_raw()
        out: List[JobPosting] = []
        for obj in raw_jobs:
            posting = self._to_posting(obj)
            if posting:
                out.append(posting)
            if self.limit and len(out) >= self.limit:
                break
        return out
