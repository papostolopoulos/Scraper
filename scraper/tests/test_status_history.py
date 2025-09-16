from scraper.jobminer.db import JobDB
from scraper.jobminer.models import JobPosting
import uuid, datetime as dt


def make_job():
    return JobPosting(
        job_id=str(uuid.uuid4()),
        title="Engineer",
        company_name="ACME",
        location="Remote",
        work_mode="remote",
        collected_at=dt.datetime.utcnow(),
        employment_type="Full-time",
        seniority_level="Mid",
        skills_extracted=[],
        description_raw="desc",
        description_clean="desc",
        apply_method="external",
        apply_url="http://example.com",
        recruiter_profiles=[],
        benefits=[],
        score_total=0.5,
        score_breakdown={"skill":0.5},
        status="new",
    )


def test_status_history_and_funnel(tmp_path):
    dbfile = tmp_path/"db.sqlite"
    db = JobDB(dbfile)
    job = make_job()
    db.upsert_jobs([job])
    # change statuses
    db.update_status(job.job_id, "reviewed")
    db.update_status(job.job_id, "shortlisted")
    db.update_status(job.job_id, "applied")
    hist = db.fetch_history(job.job_id, limit=10)
    statuses = [h["to_status"] for h in hist][::-1]
    assert statuses == ["reviewed","shortlisted","applied"]
    funnel = db.funnel_metrics()
    assert funnel["reviewed"] == 1
    assert funnel["shortlisted"] == 1
    assert funnel["applied"] == 1
    assert funnel["review_rate"] == 1.0
    assert funnel["shortlist_rate"] == 1.0
    assert funnel["apply_rate"] == 1.0
