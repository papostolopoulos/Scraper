from __future__ import annotations
"""Lever public postings adapter.

Uses Lever's unauthenticated public postings endpoint:
  https://api.lever.co/v0/postings/{company_slug}?mode=json

Each posting object commonly includes:
  id, text (title), hostedUrl, categories {location, team, commitment}, createdAt (ms epoch),
  lists (array of sections with text/ html), descriptionHtml, descriptionPlain, additional

We merge description pieces preferring descriptionHtml, then list section HTML, then plain text.

Config example:
  - name: lever_demo
    enabled: true
    module: scraper.jobminer.sources.lever_source
    class: LeverSource
    options:
      company_slug: exampleco
      limit: 150

Field mapping:
  job_id            -> posting['id']
  title             -> posting['text']
  company_name      -> override option company_name or slug-derived
  location          -> categories.location
  employment_type   -> categories.commitment
  description_raw   -> combined HTML/plain
  description_clean -> stripped HTML
  posted_at         -> createdAt epoch → date
  apply_url         -> hostedUrl
  work_mode         -> heuristic from content
"""
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime, timezone
import httpx

from ..models import JobPosting
from .adzuna_source import _strip_html, _infer_work_mode


def _epoch_ms_to_date(v):
    try:
        if v is None:
            return None
        # Lever createdAt is ms epoch
        if isinstance(v, (int, float)):
            if v > 10_000_000_000:  # ms vs sec
                v = v / 1000.0
            dt = datetime.fromtimestamp(v, timezone.utc)
            return dt.date()
    except Exception:
        return None
    return None


@dataclass
class LeverSource:
    name: str
    company_slug: str
    limit: int = 200
    company_name: Optional[str] = None

    def fetch(self) -> List[JobPosting]:
        url = f"https://api.lever.co/v0/postings/{self.company_slug}?mode=json"
        items: List[JobPosting] = []
        try:
            with httpx.Client(timeout=20.0, headers={"Accept": "application/json"}) as client:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return items
        postings = data if isinstance(data, list) else []
        for p in postings[: self.limit]:
            try:
                job_id = p.get("id") or p.get("hostedUrl")
                title = p.get("text") or ""
                categories = p.get("categories") or {}
                location = categories.get("location") if isinstance(categories, dict) else None
                employment_type = categories.get("commitment") if isinstance(categories, dict) else None
                # Compose description
                desc_html = p.get("descriptionHtml") or ""
                lists = p.get("lists") or []
                list_html_parts = []
                if isinstance(lists, list):
                    for section in lists:
                        if not isinstance(section, dict):
                            continue
                        html = section.get("content") or section.get("text") or ""
                        if html:
                            list_html_parts.append(str(html))
                if list_html_parts:
                    desc_html += "\n" + "\n".join(list_html_parts)
                if not desc_html:
                    desc_html = p.get("descriptionPlain") or ""
                posted_at = _epoch_ms_to_date(p.get("createdAt"))
                company_display = self.company_name or self.company_slug.replace('-', ' ').title()
                job_posting = JobPosting(
                    job_id=str(job_id),
                    title=title,
                    company_name=company_display,
                    location=location,
                    employment_type=employment_type,
                    work_mode=_infer_work_mode(title, desc_html),
                    posted_at=posted_at,
                    description_raw=desc_html,
                    description_clean=_strip_html(desc_html),
                    apply_method="external",
                    apply_url=p.get("hostedUrl"),
                )
                items.append(job_posting)
            except Exception:
                continue
        return items
