import json
from fastapi.testclient import TestClient
from scraper.web.server import app, JobDB
from scraper.jobminer.models import JobPosting

def seed_job(db: JobDB, **overrides):
    import datetime as dt
    base = dict(
        job_id='job1', title='Data Engineer', company_name='Acme', page_title=None,
        company_linkedin_id=None, location='Remote', work_mode='remote',
        company_name_normalized=None, location_normalized=None, location_meta=None,
        company_map_key=None, normalization_version=None, enrichment_run_at=None,
        geocode_lat=None, geocode_lon=None, posted_at=None, collected_at=dt.datetime.utcnow(),
        employment_type='full_time', seniority_level='Mid', skills_extracted=['Python','SQL','ETL','AWS','Docker'],
        description_raw='x', description_clean='x', apply_method=None, apply_url='http://example.com',
        recruiter_profiles=[], offered_salary_min=None, offered_salary_max=None, offered_salary_currency=None,
        benefits=[], score_total=87.5, score_breakdown={'skill':1.0}, status='new',
        skills_meta={'semantic_added':[{'skill':'Airflow'}], 'overlap_added':[{'skill':'Pipelines'}]}, provenance=['adzuna']
    )
    base.update(overrides)
    job = JobPosting(**base)
    db.upsert_jobs([job])
    db.update_scores(job)

def test_job_details_endpoint(tmp_path):
    db_file = tmp_path / 'db.sqlite'
    db = JobDB(db_file)
    seed_job(db)
    client = TestClient(app)
    resp = client.get(f'/api/job_details?limit=10&db_path={db_file.as_posix()}')
    assert resp.status_code == 200
    data = resp.json()
    assert 'jobs' in data
    assert data['count'] >= 1
    first = data['jobs'][0]
    assert first['top_matched'][:2] == ['Python','SQL']
    # semantic_only should contain Airflow
    assert 'Airflow' in first.get('semantic_only', [])
    # overlap_added should list Pipelines
    assert 'Pipelines' in first.get('overlap_added', [])
