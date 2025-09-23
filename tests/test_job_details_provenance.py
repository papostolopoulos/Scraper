from fastapi.testclient import TestClient
from scraper.web.server import app, JobDB
from scraper.jobminer.models import JobPosting

def seed(db: JobDB, job_id: str, provenance):
    import datetime as dt
    job = JobPosting(
        job_id=job_id,
        title='Engineer',
        company_name='Acme',
        page_title=None, company_linkedin_id=None,
        location='Remote', work_mode='remote',
        company_name_normalized=None, location_normalized=None, location_meta=None,
        company_map_key=None, normalization_version=None, enrichment_run_at=None,
        geocode_lat=None, geocode_lon=None, posted_at=None, collected_at=dt.datetime.utcnow(),
        employment_type='full_time', seniority_level='Mid', skills_extracted=['Python','SQL'],
        description_raw='d', description_clean='d', apply_method=None, apply_url='http://example.com',
        recruiter_profiles=[], offered_salary_min=None, offered_salary_max=None, offered_salary_currency=None,
        benefits=[], score_total=50.0, score_breakdown={'skill':1.0}, status='new',
        skills_meta={'semantic_added':[], 'overlap_added':[]}, provenance=provenance
    )
    db.upsert_jobs([job]); db.update_scores(job)

def test_job_details_provenance(tmp_path):
    db_file = tmp_path / 'db.sqlite'
    db = JobDB(db_file)
    seed(db, 'j1', ['adzuna'])
    seed(db, 'j2', ['adzuna','lever','greenhouse','remotive'])
    client = TestClient(app)
    resp = client.get(f'/api/job_details?limit=10&db_path={db_file.as_posix()}')
    assert resp.status_code == 200
    data = resp.json()
    jobs = {j['job_id']: j for j in data['jobs']}
    assert jobs['j1']['provenance'] == ['adzuna']
    assert jobs['j2']['provenance'][0] == 'adzuna'
    assert len(jobs['j2']['provenance']) == 4
