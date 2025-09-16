from __future__ import annotations
from typing import List
from ..models import JobPosting
from datetime import datetime, timezone


class MockJobSource:
    """Generate synthetic job postings for testing multi-source ingestion.

    Options:
      count: number of jobs to emit
      title: base title prefix
    """
    def __init__(self, name: str, count: int = 3, title: str = "Mock Engineer"):
        self.name = name
        self.count = count
        self.title = title

    def fetch(self) -> List[JobPosting]:
        jobs: List[JobPosting] = []
        for i in range(self.count):
            jobs.append(JobPosting(
                job_id=f"{i}",
                title=f"{self.title} {i}",
                company_name="DemoCo",
                location="Remote",
                work_mode="remote",
                description_raw="Synthetic job for testing",
                description_clean="Synthetic job for testing",
                collected_at=datetime.now(timezone.utc),
            ))
        return jobs
