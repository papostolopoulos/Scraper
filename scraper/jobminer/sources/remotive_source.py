from __future__ import annotations
"""Remotive API lightweight source (fallback).

Public remote jobs API docs: https://remotive.com/api/remote-jobs
We filter by search term (what) and optionally limit count. This is
used as a fallback provider when Adzuna returns few or zero results.

NOTE: This source is intentionally minimal and may be extended later
with richer normalization or additional filters.
"""
from typing import List, Optional
import httpx
from dataclasses import dataclass
from datetime import datetime
from .adzuna_source import _strip_html, _infer_work_mode, _parse_created  # reuse helpers
from ..models import JobPosting

@dataclass
class RemotiveSource:
    name: str = "remotive"
    what: Optional[str] = None
    limit: int = 50

    def fetch(self) -> List[JobPosting]:
        base = "https://remotive.com/api/remote-jobs"
        params = {}
        if self.what:
            params["search"] = self.what
        items: List[JobPosting] = []
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.get(base, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return items
        jobs = data.get("jobs", []) if isinstance(data, dict) else []
        for r in jobs[: self.limit]:
            try:
                job = JobPosting(
                    job_id=str(r.get("id") or r.get("url")),
                    title=r.get("title") or "",
                    company_name=r.get("company_name") or r.get("company") or "",
                    location=r.get("candidate_required_location") or r.get("location"),
                    work_mode="remote",  # Remotive focuses on remote jobs
                    posted_at=_parse_created(r.get("publication_date")),
                    employment_type=r.get("job_type"),
                    seniority_level=None,
                    description_raw=r.get("description"),
                    description_clean=_strip_html(r.get("description")),
                    apply_method="external",
                    apply_url=r.get("url"),
                    offered_salary_min=None,
                    offered_salary_max=None,
                    offered_salary_currency=None,
                    geocode_lat=None,
                    geocode_lon=None,
                )
                items.append(job)
            except Exception:
                continue
        return items
