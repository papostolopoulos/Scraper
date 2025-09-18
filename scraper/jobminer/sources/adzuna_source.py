from __future__ import annotations
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
import os
import re

import httpx
class AdzunaError(Exception):
    """Base Adzuna error."""


class AdzunaAuthError(AdzunaError):
    pass


class AdzunaRateLimitError(AdzunaError):
    pass


class AdzunaHTTPError(AdzunaError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class AdzunaNetworkError(AdzunaError):
    pass

from ..models import JobPosting


def _strip_html(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    # Very light HTML stripper
    return re.sub(r"<[^>]+>", " ", text)


def _infer_work_mode(title: str, description: str | None) -> str:
    t = (title or "") + "\n" + (description or "")
    tl = t.lower()
    if "remote" in tl:
        return "remote"
    if "hybrid" in tl:
        return "hybrid"
    return "onsite"


def _parse_created(dt_str: str | None):
    if not dt_str:
        return None
    try:
        # Adzuna returns ISO like '2025-09-18T12:34:56Z'
        if dt_str.endswith('Z'):
            dt_str = dt_str.replace('Z', '+00:00')
        dt = datetime.fromisoformat(dt_str)
        return dt.date()
    except Exception:
        return None


@dataclass
class AdzunaSource:
    """Adzuna API job source.

    Minimal search wrapper used by the Web MVP. Credentials are read from args or env
    variables ADZUNA_APP_ID / ADZUNA_APP_KEY when omitted.
    """

    name: str
    app_id: Optional[str] = None
    app_key: Optional[str] = None
    country: str = "us"
    what: Optional[str] = None
    where: Optional[str] = None
    distance: Optional[int] = None
    results_per_page: int = 50
    max_pages: int = 2
    max_days_old: Optional[int] = None  # limit by recency
    contract_time: Optional[str] = None  # full_time | part_time
    contract_type: Optional[str] = None  # permanent | contract

    def _cred(self):
        app_id = self.app_id or os.getenv('ADZUNA_APP_ID')
        app_key = self.app_key or os.getenv('ADZUNA_APP_KEY')
        if not app_id or not app_key:
            raise RuntimeError("Missing Adzuna credentials. Set ADZUNA_APP_ID and ADZUNA_APP_KEY.")
        return app_id, app_key

    def fetch(self) -> List[JobPosting]:
        app_id, app_key = self._cred()
        base = f"https://api.adzuna.com/v1/api/jobs/{self.country}/search"
        headers = {"Accept": "application/json"}
        items: List[JobPosting] = []
        pages = max(1, int(self.max_pages))
        per = max(1, min(100, int(self.results_per_page)))
        # Build base params
        base_params: dict[str, str | int] = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": per,
            "content-type": "application/json",
        }
        if self.what:
            base_params["what"] = self.what
        if self.where:
            base_params["where"] = self.where
        if self.distance:
            base_params["distance"] = int(self.distance)
        if self.max_days_old:
            base_params["max_days_old"] = int(self.max_days_old)
        if self.contract_time in ("full_time", "part_time"):
            base_params["contract_time"] = self.contract_time
        if self.contract_type in ("permanent", "contract"):
            base_params["contract_type"] = self.contract_type

        try:
            with httpx.Client(timeout=20.0, headers=headers) as client:
                for page in range(1, pages + 1):
                    url = f"{base}/{page}"
                    resp = client.get(url, params=base_params)
                    status = resp.status_code
                    if status in (401, 403):
                        raise AdzunaAuthError("Unauthorized (check ADZUNA_APP_ID / KEY and account permissions)")
                    if status == 429:
                        raise AdzunaRateLimitError("Rate limited by Adzuna (HTTP 429)")
                    if 400 <= status < 600 and status not in (200,):
                        # Generic upstream failure
                        raise AdzunaHTTPError(status, f"Adzuna upstream error {status}")
                    resp.raise_for_status()
                    try:
                        data = resp.json()
                    except Exception:
                        raise AdzunaHTTPError(status, "Invalid JSON from Adzuna")
                    results = data.get("results", []) if isinstance(data, dict) else []
                    if not results:
                        break
                    for r in results:
                        try:
                            job = JobPosting(
                                job_id=str(r.get("id") or r.get("adref") or r.get("redirect_url")),
                                title=r.get("title") or "",
                                company_name=(r.get("company", {}) or {}).get("display_name", ""),
                                location=(r.get("location", {}) or {}).get("display_name"),
                                work_mode=_infer_work_mode(r.get("title", ""), r.get("description")),
                                posted_at=_parse_created(r.get("created")),
                                employment_type=r.get("contract_time"),
                                seniority_level=None,
                                description_raw=r.get("description"),
                                description_clean=_strip_html(r.get("description")),
                                apply_method="external",
                                apply_url=r.get("redirect_url"),
                                offered_salary_min=r.get("salary_min"),
                                offered_salary_max=r.get("salary_max"),
                                offered_salary_currency=(r.get("salary_currency") or ("USD" if self.country.lower()=="us" else None)),
                                geocode_lat=r.get("latitude"),
                                geocode_lon=r.get("longitude"),
                            )
                            items.append(job)
                        except Exception:
                            continue
                    # Stop early if fewer than requested
                    if len(results) < per:
                        break
        except httpx.RequestError as e:
            raise AdzunaNetworkError(f"Network error contacting Adzuna: {e}") from e
        return items
