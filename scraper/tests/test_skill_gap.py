import os
from pathlib import Path
from scraper.jobminer.skill_gap import compute_skill_gaps
from scraper.jobminer.models import JobPosting
from scraper.jobminer.exporter import Exporter
from scraper.jobminer.db import JobDB

def _job(id, skills):
    return JobPosting(job_id=str(id), title='T', company_name='C', skills_extracted=skills, description_raw='d', description_clean='d')

def test_compute_skill_gaps_simple():
    jobs = [_job(1,['python','sql','pandas']), _job(2,['python','spark','airflow']), _job(3,['python','airflow','dbt'])]
    resume = ['python','sql']
    gaps = compute_skill_gaps(jobs, resume, min_freq=2)
    # airflow appears in 2 jobs, spark and dbt only once
    assert any(g['skill']=='airflow' and g['count']==2 for g in gaps)
    assert all(g['skill']!='spark' for g in gaps)
    assert all(g['skill']!='dbt' for g in gaps)


def test_export_writes_skill_gap_csv(tmp_path: Path, monkeypatch):
    # Prepare DB with jobs; mark some shortlisted via score_total
    db = JobDB(':memory:')
    j1 = JobPosting(job_id='a', title='Data Eng', company_name='Acme', skills_extracted=['python','spark','airflow'], score_total=0.75, skills_meta={'resume_overlap':['python']})
    j2 = JobPosting(job_id='b', title='Data Eng', company_name='Acme', skills_extracted=['python','airflow','dbt'], score_total=0.72, skills_meta={'resume_overlap':['python']})
    j3 = JobPosting(job_id='c', title='Data Eng', company_name='Acme', skills_extracted=['python','sql'], score_total=0.40, skills_meta={'resume_overlap':['python']})
    db.upsert_jobs([j1,j2,j3])
    exp = Exporter(db, tmp_path, stream=True)
    artefacts = exp.export_all()
    gap_path = artefacts.get('skill_gaps')
    assert gap_path is not None and gap_path.exists()
    content = gap_path.read_text().splitlines()
    # header + at least airflow line
    assert 'airflow' in '\n'.join(content)
    # skill present only once (dbt) should be absent
    assert 'dbt' not in '\n'.join(content)

def test_export_writes_skill_gap_details_json(tmp_path: Path):
    from scraper.jobminer.models import JobPosting
    from scraper.jobminer.db import JobDB
    db = JobDB(':memory:')
    j1 = JobPosting(job_id='a', title='Data Eng', company_name='Acme', skills_extracted=['python','spark','airflow'], score_total=0.75, skills_meta={'resume_overlap':['python']})
    j2 = JobPosting(job_id='b', title='Data Eng', company_name='Acme', skills_extracted=['python','airflow','dbt'], score_total=0.72, skills_meta={'resume_overlap':['python']})
    db.upsert_jobs([j1,j2])
    exp = Exporter(db, tmp_path, stream=True)
    artefacts = exp.export_all()
    details_path = artefacts.get('skill_gaps_details')
    assert details_path and details_path.exists(), 'Expected skill_gaps_details.json to be written'
    import json
    data = json.loads(details_path.read_text())
    assert isinstance(data, list) and data, 'Details JSON should contain a non-empty list'
    first = data[0]
    # minimal required keys
    assert 'skill' in first and 'count' in first and 'shortlist_pct' in first
    # priority_score may or may not exist depending on weights; tolerate absence but if present ensure numeric
    if 'priority_score' in first:
        assert isinstance(first['priority_score'], (int,float))


def test_skill_gap_category_inclusion(tmp_path: Path):
    # Ensure taxonomy file is present (created in config). Use skills that map.
    jobs = [_job(1,['python','airflow']), _job(2,['python','airflow','spark'])]
    resume = ['python']
    gaps = compute_skill_gaps(jobs, resume, min_freq=1)
    airflow_entry = next(g for g in gaps if g['skill']=='airflow')
    assert 'category' in airflow_entry and airflow_entry['category'] in ('workflow','data_engineering')

def test_export_skill_gap_category(tmp_path: Path):
    db = JobDB(':memory:')
    # airflow appears in both shortlisted jobs (freq=2) and is not on resume -> should be exported
    j1 = JobPosting(job_id='a', title='Data Eng', company_name='Acme', skills_extracted=['python','airflow'], score_total=0.80, skills_meta={'resume_overlap':['python']})
    j2 = JobPosting(job_id='b', title='Data Eng', company_name='Acme', skills_extracted=['python','airflow','spark'], score_total=0.79, skills_meta={'resume_overlap':['python']})
    db.upsert_jobs([j1,j2])
    exp = Exporter(db, tmp_path, stream=True)
    artefacts = exp.export_all()
    gap_path = artefacts['skill_gaps']
    text = gap_path.read_text().lower()
    assert 'airflow' in text and ('workflow' in text or 'data_engineering' in text)


def test_priority_score_ordering(tmp_path: Path):
    # Create three shortlisted jobs with varying scores to exercise weighting.
    from scraper.jobminer.skill_gap import compute_skill_gaps
    scores = [0.9, 0.8, 0.7]
    jobs = []
    # airflow (workflow cat weight 1.1) appears in two high scoring jobs; spark (1.3) appears in one high; terraform (1.2) appears in all three
    from scraper.jobminer.models import JobPosting
    jobs.append(JobPosting(job_id='1', title='t', company_name='c', skills_extracted=['airflow','terraform'], score_total=scores[0], skills_meta={'resume_overlap':['python']}))
    jobs.append(JobPosting(job_id='2', title='t', company_name='c', skills_extracted=['airflow','spark','terraform'], score_total=scores[1], skills_meta={'resume_overlap':['python']}))
    jobs.append(JobPosting(job_id='3', title='t', company_name='c', skills_extracted=['terraform'], score_total=scores[2], skills_meta={'resume_overlap':['python']}))
    resume = ['python']
    gaps = compute_skill_gaps(jobs, resume, min_freq=1)
    # ensure priority_score exists
    assert all('priority_score' in g for g in gaps)
    # terraform should likely top due to frequency 3 despite moderate cat weight; check ordering deterministic
    skills_order = [g['skill'] for g in gaps]
    assert skills_order[0] in ('terraform','airflow')
    # frequency-driven ordering fallback for unknown ties
    assert 'spark' in skills_order
