import json
from pathlib import Path
import types
import httpx
import pytest

from scraper.jobminer.sources.adzuna_source import (
    AdzunaSource,
    _infer_work_mode,
    _parse_created,
    AdzunaAuthError,
    AdzunaRateLimitError,
    AdzunaHTTPError,
)

class DummyResp:
    def __init__(self, status_code:int, payload:dict):
        self.status_code = status_code
        self._payload = payload
    def json(self):
        return self._payload
    def raise_for_status(self):
        if self.status_code >=400:
            raise httpx.HTTPStatusError("boom", request=None, response=types.SimpleNamespace(status_code=self.status_code))

class DummyClient:
    def __init__(self, sequence):
        self.sequence = sequence
        self.calls = 0
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def get(self, url, params):
        item = self.sequence[self.calls]
        self.calls += 1
        return DummyResp(*item)

@pytest.mark.parametrize("title,desc,expected",[
    ("Senior Engineer (Remote)", None, "remote"),
    ("Hybrid Data Scientist", "", "hybrid"),
    ("Data Analyst", "Onsite role", "onsite"),
])
def test_infer_work_mode(title, desc, expected):
    assert _infer_work_mode(title, desc) == expected

@pytest.mark.parametrize("raw,expected",[
    ("2025-09-18T12:34:56Z", "2025-09-18"),
    ("2025-09-18T12:34:56+00:00", "2025-09-18"),
    (None, None),
    ("bad", None),
])
def test_parse_created(raw, expected):
    d = _parse_created(raw)
    if expected is None:
        assert d is None
    else:
        assert str(d) == expected


def test_fetch_happy(monkeypatch):
    seq = [
        (200, {"results": [
            {"id": 1, "title": "Data Engineer Remote", "company": {"display_name":"ACME"}, "location": {"display_name":"NY"}, "description":"Remote role", "created":"2025-09-18T00:00:00Z"}
        ]})
    ]
    monkeypatch.setattr("httpx.Client", lambda timeout, headers: DummyClient(seq))
    src = AdzunaSource(name="adzuna", app_id="x", app_key="y", what="data engineer")
    items = src.fetch()
    assert len(items) == 1
    assert items[0].title.startswith("Data Engineer")


def test_fetch_auth_error(monkeypatch):
    seq = [(401, {"results": []})]
    monkeypatch.setattr("httpx.Client", lambda timeout, headers: DummyClient(seq))
    src = AdzunaSource(name="adzuna", app_id="x", app_key="y")
    with pytest.raises(AdzunaAuthError):
        src.fetch()


def test_fetch_rate_limit(monkeypatch):
    seq = [(429, {"results": []})]
    monkeypatch.setattr("httpx.Client", lambda timeout, headers: DummyClient(seq))
    src = AdzunaSource(name="adzuna", app_id="x", app_key="y")
    with pytest.raises(AdzunaRateLimitError):
        src.fetch()


def test_fetch_upstream_http(monkeypatch):
    seq = [(500, {"error":"server"})]
    monkeypatch.setattr("httpx.Client", lambda timeout, headers: DummyClient(seq))
    src = AdzunaSource(name="adzuna", app_id="x", app_key="y")
    with pytest.raises(AdzunaHTTPError):
        src.fetch()
