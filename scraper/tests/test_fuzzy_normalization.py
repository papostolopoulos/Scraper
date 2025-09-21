import os
from datetime import datetime
from scraper.jobminer.db import JobDB
from scraper.jobminer.models import JobPosting
from scraper.jobminer.dedupe import build_signature


def _job(id_, company, title, location):
    return JobPosting(
        job_id=id_,
        title=title,
        company_name=company,
        location=location,
        work_mode='remote',
        collected_at=datetime.utcnow(),
        description_raw='desc',
        description_clean='some engineering work',
        employment_type='full-time',
        seniority_level='senior',
        skills_extracted=[],
        apply_method='url',
        apply_url='http://example.com',
        recruiter_profiles=[],
        offered_salary_min=None,
        offered_salary_max=None,
        offered_salary_currency=None,
        benefits=[],
        score_total=0.0,
        score_breakdown=None,
        status='new'
    )


def test_fuzzy_signature_merges_when_enabled(monkeypatch):
    monkeypatch.setenv('JOBMINER_FUZZY_NORMALIZATION', '1')
    # reload settings to apply toggle
    from importlib import reload
    from scraper.jobminer import settings as settings_mod
    reload(settings_mod)
    from scraper.jobminer.dedupe import build_signature as bs

    a = _job('a','Acme Inc','Sr Data Eng.','San Francisco, CA, USA')
    b = _job('b','The Acme, Inc.','Senior Data Engineer','San Francisco CA')
    sig_a = bs(a)
    sig_b = bs(b)
    assert sig_a == sig_b, (sig_a, sig_b)


def test_fuzzy_signature_different_when_disabled(monkeypatch):
    monkeypatch.delenv('JOBMINER_FUZZY_NORMALIZATION', raising=False)
    from importlib import reload
    from scraper.jobminer import settings as settings_mod
    reload(settings_mod)
    from scraper.jobminer.dedupe import build_signature as bs
    a = _job('a','Acme Inc','Sr Data Eng.','San Francisco, CA, USA')
    b = _job('b','The Acme, Inc.','Senior Data Engineer','San Francisco CA')
    sig_a = bs(a)
    sig_b = bs(b)
    assert sig_a != sig_b, (sig_a, sig_b)


def test_fuzzy_does_not_merge_distinct_companies(monkeypatch):
    monkeypatch.setenv('JOBMINER_FUZZY_NORMALIZATION', '1')
    from importlib import reload
    from scraper.jobminer import settings as settings_mod
    reload(settings_mod)
    from scraper.jobminer.dedupe import build_signature as bs
    a = _job('a','Acme Data','Senior Engineer','New York, NY')
    b = _job('b','Acme Data Labs','Senior Engineer','New York, NY')
    sig_a = bs(a)
    sig_b = bs(b)
    assert sig_a != sig_b, (sig_a, sig_b)
