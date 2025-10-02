from datetime import datetime, timedelta, timezone
from scraper.jobminer.models import JobPosting
from scraper.jobminer.scoring import compute_recency_score, aggregate_score


def test_recency_score_decay():
    now = datetime.now(timezone.utc)
    fresh = compute_recency_score(now.date(), now)
    old = compute_recency_score((now - timedelta(days=10)).date(), now)
    assert fresh > old
    assert 0.0 <= old <= 1.0


def test_seniority_penalty_affects_total():
    job = JobPosting(job_id='1', title='X', company_name='Y', seniority_level='Senior')
    weights = {'skill':0.0,'semantic':0.0,'recency':0.0,'seniority':1.0,'company':0.0}
    # Target excludes 'Senior' so penalty applied -> component < 1.0
    aggregate_score(job, [], '', weights, target_seniority=['Junior','Mid'])
    assert job.score_total is not None and job.score_total < 1.0
    # Including Senior removes penalty -> component == 1.0
    job2 = JobPosting(job_id='2', title='X', company_name='Y', seniority_level='Senior')
    aggregate_score(job2, [], '', weights, target_seniority=['Senior'])
    assert job2.score_total == 1.0
