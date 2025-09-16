from scraper.jobminer.enrich import normalize_company, parse_location, enrich_jobs
from scraper.jobminer.dedupe import detect_duplicates
from scraper.jobminer.models import JobPosting
from scraper.jobminer.enrich import geocode_location
from scraper.jobminer.db import JobDB
from scraper.jobminer.exporter import Exporter
from datetime import datetime, timezone
from pathlib import Path
import tempfile, json
import pandas as pd


def test_normalize_company_suffix_and_article():
    mapping = { 'acme corp': 'Acme' }
    assert normalize_company('The Acme Corp', mapping) == 'Acme'
    # mapping override wins
    assert normalize_company('ACME CORP', mapping) == 'Acme'


def test_parse_location_remote():
    loc, meta = parse_location('Remote - US')
    assert loc == 'Remote'
    assert meta and meta.get('mode_hint') == 'remote'


def test_parse_location_city_state_country():
    canon, meta = parse_location('Seattle, WA, United States')
    assert 'Seattle' in canon
    assert meta and meta.get('country') == 'USA'


def test_enrich_jobs_sets_fields():
    job = JobPosting(job_id='1', title='Data Engineer', company_name='ACME Corp', location='Boston, MA, United States')
    jobs = [job]
    updated = enrich_jobs(jobs, { 'acme corp': 'Acme' })
    assert updated == 1
    assert job.company_name_normalized == 'Acme'
    assert job.location_normalized.startswith('Boston')
    assert job.location_meta and job.location_meta.get('country') == 'USA'


def test_detect_duplicates_marks_later():
    j1 = JobPosting(job_id='a', title='Senior Data Engineer', company_name='Acme', location='Boston, MA, United States')
    j2 = JobPosting(job_id='b', title='Senior Data Engineer', company_name='Acme', location='Boston, MA, United States')
    jobs = [j1, j2]
    # simulate order so j1 earlier
    dups = detect_duplicates(jobs)
    assert dups == 1
    assert j1.status != 'duplicate'
    assert j2.status == 'duplicate'


def test_enrichment_idempotent():
    job = JobPosting(job_id='x', title='Engineer', company_name='The Acme Corp', location='Seattle, WA, United States')
    jobs = [job]
    mapping = {'acme corp': 'Acme'}
    first = enrich_jobs(jobs, mapping)
    second = enrich_jobs(jobs, mapping)
    assert first == 1
    assert second == 0  # no further changes
    assert job.company_name_normalized == 'Acme'
    # No side-effects beyond enrichment in this test.
