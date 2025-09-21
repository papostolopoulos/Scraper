from __future__ import annotations
"""Greenhouse public board adapter.

This adapter fetches job postings from a company's public Greenhouse board.
It relies solely on publicly exposed JSON endpoints (no authentication) and
therefore respects Terms of Service when used responsibly (low frequency,
no parallel hammering, user-provided company slug).

Greenhouse exposes two helpful endpoints:
  1. https://boards.greenhouse.io/{company_slug}/embed/jobs (HTML w/ JSON)
  2. https://boards.greenhouse.io/{company_slug}/embed/jobs/json (pure JSON)

We call the JSON endpoint directly. Structure (simplified):
{
  "jobs": [
     {
       "id": 123,
       "internal_job_id": 456,
       "title": "Data Engineer",
       "updated_at": "2025-09-17T21:13:07-04:00",
       "content": "<p>HTML description</p>",
       "absolute_url": "https://boards.greenhouse.io/.../jobs/123",
       "metadata": [...],
       "departments": [{"name": "Engineering"}],
       "offices": [{"name": "Remote - US"}],
       ...
     }
  ]
}

Config example (sources.yml):

  - name: gh_demo
    enabled: true
    module: scraper.jobminer.sources.greenhouse_source
    class: GreenhouseSource
    options:
      company_slug: examplecompany
      limit: 100

Fields mapped to JobPosting:
  job_id            -> str(job['id'])
  title             -> job['title']
  company_name      -> provided company_slug (canonical), override via option company_name
  location          -> first office name if present
  posted_at         -> parsed from updated_at (date portion) when available
  description_raw   -> job['content'] (HTML)
  description_clean -> stripped HTML (rough)
  apply_url         -> absolute_url
  work_mode         -> heuristic from title + description

NOTE: Salary rarely appears in these public postings; left blank unless simple extraction
is added later.
"""
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
import re
import httpx
import logging

from ..models import JobPosting
from .adzuna_source import _strip_html, _infer_work_mode, _parse_created


def _parse_updated(ts: str | None):
    if not ts:
        return None
    # Greenhouse timestamps often have timezone offsets like 2025-09-17T21:13:07-04:00
    try:
        # Replace trailing Z if present for consistency (rare here)
        if ts.endswith('Z'):
            ts = ts.replace('Z', '+00:00')
        dt = datetime.fromisoformat(ts)
        return dt.date()
    except Exception:
        return None


@dataclass
class GreenhouseSource:
    name: str
    company_slug: str
    limit: int = 200
    company_name: Optional[str] = None  # override displayed company name

    def fetch(self) -> List[JobPosting]:
        url = f"https://boards.greenhouse.io/{self.company_slug}/embed/jobs/json"
        items: List[JobPosting] = []
        logger = logging.getLogger("sources.greenhouse")
        try:
            with httpx.Client(timeout=20.0, headers={"Accept": "application/json"}) as client:
                logger.info("greenhouse_request url=%s", url)
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            # Log and return empty list (network or parsing issue)
            logger.warning("greenhouse_fetch_error slug=%s err=%s", self.company_slug, e)
            return items
        if isinstance(data, dict):
            jobs = data.get("jobs", [])
        elif isinstance(data, list):
            # Fallback: some tests or edge endpoints may return the jobs array directly
            jobs = data
        else:
            jobs = []
        logger.info("greenhouse_jobs count=%d", len(jobs) if isinstance(jobs, list) else -1)
        for j in jobs[: self.limit]:
            try:
                job_id = j.get("id") or j.get("internal_job_id") or j.get("absolute_url") or j.get("hostedUrl")
                # Fallback to Lever-style 'text' if 'title' missing (test robustness)
                title = j.get("title") or j.get("text") or ""
                content = j.get("content") or j.get("descriptionHtml") or j.get("descriptionPlain") or ""
                offices = j.get("offices") or []
                location = None
                if offices and isinstance(offices, list):
                    # prefer a non-empty name
                    for o in offices:
                        n = o.get("name") if isinstance(o, dict) else None
                        if n:
                            location = n
                            break
                # fallback: sometimes location in metadata or Lever-style categories
                if not location:
                    metadata = j.get("metadata") or []
                    if isinstance(metadata, list):
                        for m in metadata:
                            if isinstance(m, dict) and m.get("name", "").lower() == "location":
                                location = m.get("value")
                                if location:
                                    break
                if not location:
                    categories = j.get("categories") or {}
                    if isinstance(categories, dict):
                        loc2 = categories.get("location")
                        if loc2:
                            location = loc2
                posted_at = _parse_updated(j.get("updated_at")) or _parse_created(j.get("updated_at"))
                company_display = self.company_name or self.company_slug.replace('-', ' ').title()
                job_posting = JobPosting(
                    job_id=str(job_id),
                    title=title,
                    company_name=company_display,
                    location=location,
                    work_mode=_infer_work_mode(title, content),
                    posted_at=posted_at,
                    description_raw=content,
                    description_clean=_strip_html(content),
                    apply_method="external",
                    apply_url=j.get("absolute_url"),
                )
                items.append(job_posting)
            except Exception as e:
                logger.warning("greenhouse_parse_error err=%s", e)
                continue
        return items
