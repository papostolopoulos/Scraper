from scraper.jobminer.sources.base import load_sources, collect_from_sources
from scraper.jobminer.sources.mock_source import MockJobSource
from scraper.jobminer.db import JobDB
from scraper.jobminer.models import JobPosting


class AltMockJobSource(MockJobSource):
    def fetch(self):
        jobs = super().fetch()
        # Duplicate one id intentionally to test dedupe across sources
        if jobs:
            jobs[0].job_id = "0"  # will get prefixed per source
        return jobs


def test_multi_source_dedup(tmp_path, monkeypatch):
    # Configure two sources with overlapping internal ids
    src_cfg = [
        {"name": "mock", "enabled": True, "module": "scraper.jobminer.sources.mock_source", "class": "MockJobSource", "options": {"count": 3}},
        {"name": "alt", "enabled": True, "module": "scraper.jobminer.sources.mock_source", "class": "MockJobSource", "options": {"count": 2}},
    ]
    # Monkeypatch load to use AltMock for alt
    monkeypatch.setattr("scraper.jobminer.sources.base.importlib.import_module", lambda m: __import__(m, fromlist=["dummy"]))
    # Temporarily inject AltMock into module namespace
    import scraper.jobminer.sources.mock_source as ms
    ms.AltMockJobSource = AltMockJobSource  # type: ignore
    src_cfg[1]["class"] = "AltMockJobSource"

    loaded = load_sources(src_cfg)
    collected = collect_from_sources(loaded)
    # Expect prefixes: mock:0, mock:1, mock:2, alt:0, alt:1 (no dedupe removal since prefixes differ)
    ids = {j.job_id for j in collected}
    assert len(ids) == 5
    # Insert into DB and ensure no collision
    db_path = tmp_path / "db.sqlite"
    from scraper.jobminer.db import JobDB as _JobDB
    db = _JobDB(db_path)
    db.upsert_jobs(collected)
    stored = {j.job_id for j in db.fetch_all()}
    assert ids == stored
