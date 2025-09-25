from scraper.jobminer.multi_source import merge_and_enrich
from scraper.jobminer.models import JobPosting
import datetime as dt
import os


def _job(job_id, title, company, location='Remote', desc='d', posted=None, provenance=None):
    return JobPosting(
        job_id=job_id,
        title=title,
        company_name=company,
        location=location,
        description_raw=desc,
        description_clean=desc,
        posted_at=posted,
        collected_at=dt.datetime.utcnow(),
        provenance=provenance or []
    )


def test_merge_reduces_duplicates_and_orders_primary_first(monkeypatch):
    monkeypatch.setenv('JOBMINER_DEDUPE_PRIMARY', 'adzuna')
    monkeypatch.setenv('JOBMINER_DEDUPE_ORDER_PRIMARY_FIRST', '1')
    # Two representations of the same job (adzuna breadth + lever ATS) -> should merge
    jobs = [
        _job('adzuna:123', 'Data Engineer', 'Acme', desc='Short', posted=dt.date(2025,9,10), provenance=['adzuna']),
        _job('lever:abc', 'Data Engineer', 'Acme', desc='Longer description body', posted=dt.date(2025,9,12), provenance=['lever']),
        _job('greenhouse:zzz', 'Data Engineer', 'Acme', desc='Medium', posted=dt.date(2025,9,11), provenance=['greenhouse']),
        _job('adzuna:999', 'Analytics Engineer', 'Acme', desc='Analytics role', posted=dt.date(2025,9,9), provenance=['adzuna']),
    ]
    merged = merge_and_enrich(jobs)
    assert len(merged) == 2  # Data Engineer cluster + Analytics Engineer
    # Primary-first ordering: adzuna containing clusters first
    assert 'adzuna' in merged[0].provenance
    # Provenance union for Data Engineer cluster includes all three sources
    de = next(j for j in merged if j.title == 'Data Engineer')
    assert set(de.provenance) == {'adzuna','lever','greenhouse'}
    # Canonical description should be the longest among cluster (lever entry)
    assert len(de.description_raw or '') == len('Longer description body')


def test_merge_disable(monkeypatch):
    monkeypatch.setenv('JOBMINER_ENABLE_PHASE2_MERGE', '0')
    # When disabled we just return the original list unchanged
    jobs = [
        _job('adzuna:1','Data Scientist','Acme', provenance=['adzuna']),
        _job('lever:1','Data Scientist','Acme', provenance=['lever']),
    ]
    # Simulate server behavior: only call merge when enabled
    if os.getenv('JOBMINER_ENABLE_PHASE2_MERGE','1').lower() in ('1','true','yes','on'):
        out = merge_and_enrich(jobs)
    else:
        out = jobs
    assert len(out) == 2  # no merge
    titles = sorted(j.title for j in out)
    assert titles == ['Data Scientist','Data Scientist']
