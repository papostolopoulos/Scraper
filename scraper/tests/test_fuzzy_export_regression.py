import os
from pathlib import Path
from scraper.jobminer.models import JobPosting
from scraper.jobminer.db import JobDB
from scraper.jobminer.dedupe import detect_duplicates
from scraper.jobminer.exporter import Exporter


def _make_jobs():
    # Two variants that should merge only when fuzzy normalization enabled
    j1 = JobPosting(job_id='gh:1', title='Sr Data Eng', company_name='The Acme, Inc.', location='San Francisco, CA', description_raw='a', description_clean='a')
    j2 = JobPosting(job_id='lever:2', title='Senior Data Engineer', company_name='ACME INC', location='San Francisco CA', description_raw='a', description_clean='a')
    return [j1, j2]


def _run_export(tmp_path: Path, fuzzy: bool):
    if fuzzy:
        os.environ['JOBMINER_FUZZY_NORMALIZATION']='1'
    else:
        os.environ.pop('JOBMINER_FUZZY_NORMALIZATION', None)
    db = JobDB(':memory:')
    jobs = _make_jobs()
    db.upsert_jobs(jobs)
    # Fetch fresh objects (the ones export will use), run dedupe, then persist duplicate status
    fetched = db.fetch_all()
    detect_duplicates(fetched, desc_prefix=0, enable_similarity=False)
    db.upsert_jobs(fetched)
    exp = Exporter(db, tmp_path, stream=True)
    artefacts = exp.export_all()
    csv_path = artefacts['full_csv']
    content = csv_path.read_text().splitlines()
    return content


def test_fuzzy_normalization_changes_duplicate_merge(tmp_path: Path):
    # With fuzzy OFF -> two rows (both not duplicate)
    off_rows = _run_export(tmp_path / 'off', fuzzy=False)
    # header + 2 data lines
    assert len(off_rows) == 3, off_rows
    # With fuzzy ON -> one row (second duplicate filtered out)
    on_rows = _run_export(tmp_path / 'on', fuzzy=True)
    assert len(on_rows) == 2, on_rows
