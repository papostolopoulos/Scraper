from pathlib import Path
from scraper.jobminer.sources.indeed_source import IndeedJobSource
from scraper.jobminer.sources.base import normalize_ids


def test_indeed_source_loads_sample(tmp_path):
    # Copy sample file into temp to avoid mutating original
    sample = Path('data/sample/indeed_jobs.json')
    target = tmp_path / 'indeed_jobs.json'
    target.write_text(sample.read_text(encoding='utf-8'), encoding='utf-8')
    src = IndeedJobSource(name='indeed', path=str(target))
    jobs = src.fetch()
    assert len(jobs) == 3
    # Ensure required fields populated
    for j in jobs:
        assert j.job_id and j.title and j.company_name and j.description_raw
    # Normalize IDs and ensure prefix added
    norm = normalize_ids(jobs, 'indeed')
    assert all(j.job_id.startswith('indeed:') for j in norm)
    # Company normalization test (Acme Inc. should lose Inc.)
    acme = next(j for j in norm if 'Acme' in j.company_name)
    assert acme.company_name_normalized == 'Acme'


def test_indeed_source_limit(tmp_path):
    sample = Path('data/sample/indeed_jobs.json')
    target = tmp_path / 'indeed_jobs.json'
    target.write_text(sample.read_text(encoding='utf-8'), encoding='utf-8')
    src = IndeedJobSource(name='indeed', path=str(target), limit=1)
    jobs = src.fetch()
    assert len(jobs) == 1
