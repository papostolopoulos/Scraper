import os
from pathlib import Path
import csv
import datetime as dt
from scraper.jobminer.db import JobDB
from scraper.jobminer.models import JobPosting
from scraper.jobminer.exporter import Exporter

def make_job(i, score):
    return JobPosting(
        job_id=str(i),
        title=f'Engineer {i}',
        company_name='Acme',
        location='Remote',
        work_mode='remote',
        collected_at=dt.datetime.utcnow(),
        description_raw='Python SQL Pipelines',
        description_clean='Python SQL Pipelines',
        employment_type='Full-time',
        seniority_level='Mid',
        skills_extracted=['Python','SQL'],
        score_total=score,
        score_breakdown={'skill': score*0.6, 'semantic': score*0.4},
        benefits=['Health'],
        status='new'
    )

def read_csv_rows(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def test_streaming_matches_non_streaming(tmp_path):
    db_path = tmp_path/'db.sqlite'
    db = JobDB(db_path)
    jobs = [make_job(i, 0.5 + i*0.05) for i in range(8)]
    db.upsert_jobs(jobs)
    out_dir_standard = tmp_path/'out_standard'
    out_dir_stream = tmp_path/'out_stream'

    # Non streaming
    exp_std = Exporter(db, out_dir_standard, stream=False).export_all()
    # Streaming
    os.environ['SCRAPER_STREAM_EXPORT'] = '1'
    exp_stream = Exporter(db, out_dir_stream).export_all()

    std_full = read_csv_rows(exp_std['full_csv'])
    stream_full = read_csv_rows(exp_stream['full_csv'])
    assert std_full == stream_full

    std_short = read_csv_rows(exp_std['shortlist'])
    stream_short = read_csv_rows(exp_stream['shortlist'])
    assert std_short == stream_short

    std_expl = read_csv_rows(exp_std['explanations_csv'])
    stream_expl = read_csv_rows(exp_stream['explanations_csv'])
    # Order should match because iteration order stable
    assert std_expl == stream_expl
