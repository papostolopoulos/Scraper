from datetime import datetime, timezone, timedelta
from scraper.jobminer.models import JobPosting
from scraper.jobminer.dedupe import detect_duplicates

def make_job(job_id, title, desc, minutes=0):
    return JobPosting(
        job_id=job_id,
        title=title,
        company_name='Acme',
        location='Seattle, WA',
        work_mode='remote',
        collected_at=datetime.now(timezone.utc) + timedelta(minutes=minutes),
        description_raw=desc,
        description_clean=desc,
        employment_type='Full-time',
        seniority_level='Mid',
        skills_extracted=['Python'],
        recruiter_profiles=[],
        benefits=[],
        status='new',
        score_total=0.75,
    )

def test_near_duplicate_jaccard_marks_duplicate():
    # Two descriptions with small variation (token Jaccard high)
    base = "Responsible for building distributed data pipelines and ensuring data quality across systems."
    variant = "Responsible for building distributed data pipeline and ensuring data quality across the systems."  # small changes
    a = make_job('a', 'Data Engineer', base, minutes=0)
    b = make_job('b', 'Data Engineer', variant, minutes=1)
    jobs = [a,b]
    dup = detect_duplicates(jobs, desc_prefix=0, enable_similarity=True, jaccard_min=0.8, title_fuzzy_min=85)
    assert dup == 1
    statuses = {j.job_id: j.status for j in jobs}
    assert statuses['a'] == 'new'
    assert statuses['b'] == 'duplicate'

def test_no_duplicate_when_low_similarity():
    a = make_job('c', 'Data Engineer', 'Work on ML models and dashboards', minutes=0)
    b = make_job('d', 'Data Engineer', 'Design networking hardware drivers', minutes=1)
    jobs = [a,b]
    dup = detect_duplicates(jobs, desc_prefix=0, enable_similarity=True, jaccard_min=0.85, title_fuzzy_min=90)
    assert dup == 0
    assert all(j.status == 'new' for j in jobs)
