def test_db_basic_lifecycle(jobdb):
    # Insert and fetch to exercise connection usage
    from scraper.jobminer.models import JobPosting
    job = JobPosting(job_id='x1', title='Test', company_name='Acme')
    jobdb.upsert_jobs([job])
    rows = jobdb.fetch_all()
    assert rows and rows[0].job_id == 'x1'
