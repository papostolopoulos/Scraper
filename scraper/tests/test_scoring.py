from scraper.jobminer.models import JobPosting
from scraper.jobminer.scoring import aggregate_score

def test_scoring_basic():
    job = JobPosting(
        job_id='t1',
        title='Data Analyst',
        company_name='X',
        skills_extracted=['sql','python'],
        description_clean='We need a data analyst who knows SQL and Python.'
    )
    weights = {'skill':0.4,'semantic':0.4,'recency':0.2,'seniority':0.0,'company':0.0}
    aggregate_score(job, ['sql','python','excel'], 'Experienced data analyst with SQL and Python', weights, ['Associate'])
    assert job.score_total is not None
    assert 0.4 <= job.score_total <= 1.0
