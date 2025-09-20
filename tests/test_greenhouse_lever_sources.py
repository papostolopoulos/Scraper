from pathlib import Path
import json
from scraper.jobminer.sources.greenhouse_source import GreenhouseSource
from scraper.jobminer.sources.lever_source import LeverSource
from scraper.jobminer.sources.base import _dup_signature, _canonical_text  # type: ignore

# NOTE: We import private helpers for targeted testing; acceptable within test scope.

def test_greenhouse_basic(monkeypatch):
    sample = {"jobs": [
        {"id": 101, "title": "Data Engineer", "content": "<p>Build pipelines</p>", "absolute_url": "https://boards.greenhouse.io/examplecompany/jobs/101", "updated_at": "2025-09-10T12:00:00Z", "offices": [{"name": "Remote - US"}]},
        {"id": 102, "title": "Senior Data Engineer", "content": "<p>Lead work</p>", "absolute_url": "https://boards.greenhouse.io/examplecompany/jobs/102", "updated_at": "2025-09-11T12:00:00Z"}
    ]}
    def fake_get(url):
        class R:
            status_code = 200
            def json(self_inner):
                return sample
            def raise_for_status(self_inner):
                return None
        return R()
    class DummyClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def get(self, url): return fake_get(url)
    monkeypatch.setattr("scraper.jobminer.sources.greenhouse_source.httpx.Client", DummyClient)
    src = GreenhouseSource(name="gh_example", company_slug="examplecompany", limit=10)
    jobs = src.fetch()
    assert len(jobs) == 2
    assert jobs[0].company_name == "Examplecompany"  # slug derived
    assert jobs[0].location == "Remote - US"
    assert jobs[0].apply_url.endswith("/101")


def test_lever_basic(monkeypatch):
    sample = [
        {"id": "lev1", "text": "Data Analyst", "hostedUrl": "https://jobs.lever.co/exampleco/lev1", "categories": {"location": "Remote", "commitment": "Full-time"}, "createdAt": 1757600000000, "descriptionHtml": "<p>Analyze data</p>", "lists": []},
        {"id": "lev2", "text": "Data Engineer", "hostedUrl": "https://jobs.lever.co/exampleco/lev2", "categories": {"location": "Remote"}, "createdAt": 1757605000000, "descriptionHtml": "<p>Build stuff</p>", "lists": []}
    ]
    def fake_get(url):
        class R:
            status_code = 200
            def json(self_inner):
                return sample
            def raise_for_status(self_inner):
                return None
        return R()
    class DummyClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def get(self, url): return fake_get(url)
    monkeypatch.setattr("scraper.jobminer.sources.lever_source.httpx.Client", DummyClient)
    src = LeverSource(name="lever_example", company_slug="exampleco", limit=10)
    jobs = src.fetch()
    assert len(jobs) == 2
    assert jobs[0].company_name == "Exampleco"
    assert jobs[0].employment_type == "Full-time"
    assert jobs[0].apply_url.endswith("/lev1")


def test_provenance_merge(monkeypatch):
    # Simulate two sources (gh + lever) yielding effectively the same job
    gh_sample = {"jobs": [
        {"id": 1, "title": "Data Engineer", "content": "<p>ETL pipelines</p>", "absolute_url": "https://boards.greenhouse.io/exampleco/jobs/1", "updated_at": "2025-09-10T12:00:00Z", "offices": [{"name": "Remote"}]}
    ]}
    lever_sample = [
        {"id": "lev1", "text": "Data Engineer", "hostedUrl": "https://jobs.lever.co/exampleco/lev1", "categories": {"location": "Remote", "commitment": "Full-time"}, "createdAt": 1757600000000, "descriptionHtml": "<p>ETL pipelines</p>", "lists": []}
    ]
    class DummyClientGH:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def get(self, url):
            class R:
                status_code = 200
                def json(self_inner): return gh_sample
                def raise_for_status(self_inner): return None
            return R()
    class DummyClientLever:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def get(self, url):
            class R:
                status_code = 200
                def json(self_inner): return lever_sample
                def raise_for_status(self_inner): return None
            return R()
    monkeypatch.setattr("scraper.jobminer.sources.greenhouse_source.httpx.Client", DummyClientGH)
    monkeypatch.setattr("scraper.jobminer.sources.lever_source.httpx.Client", DummyClientLever)

    from scraper.jobminer.sources.greenhouse_source import GreenhouseSource
    from scraper.jobminer.sources.lever_source import LeverSource
    from scraper.jobminer.sources.base import load_sources, collect_from_sources

    cfg = [
        {"name": "gh", "enabled": True, "module": "scraper.jobminer.sources.greenhouse_source", "class": "GreenhouseSource", "options": {"company_slug": "exampleco"}},
        {"name": "lever", "enabled": True, "module": "scraper.jobminer.sources.lever_source", "class": "LeverSource", "options": {"company_slug": "exampleco"}},
    ]
    loaded = load_sources(cfg)
    jobs = collect_from_sources(loaded)
    assert len(jobs) == 1  # merged
    j = jobs[0]
    assert set(j.provenance) == {"gh", "lever"}
    # signature stability
    sig = _dup_signature(j)
    assert sig.startswith("u:") or sig.startswith("c:")
