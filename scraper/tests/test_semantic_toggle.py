import os
from pathlib import Path
from scraper.jobminer.db import JobDB
from scraper.jobminer.models import JobPosting
from scraper.jobminer.pipeline import score_all


def make_job(desc: str):
    return JobPosting(job_id='s1', title='Role', company_name='Co', description_raw=desc, description_clean=desc)


def test_semantic_disabled_override(tmp_path, monkeypatch):
    db = JobDB(tmp_path/'db.sqlite')
    # Description with generic sentence likely to trigger semantic inference for a seed skill
    job = make_job('We collaborate on scalable distributed systems and perform data analysis for machine learning pipelines.')
    db.upsert_jobs([job])
    # Seed skills
    seed = tmp_path/'skills.txt'
    seed.write_text('distributed systems\ndata analysis\npython\n', encoding='utf-8')
    # Resume PDF placeholder
    resume = tmp_path/'resume.pdf'
    resume.write_bytes(b"%PDF-1.3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF")
    # Run with semantic enabled first
    count = score_all(db, resume, seed, semantic_override=True)
    assert count == 1
    j_enabled = db.fetch_by_id('s1')
    sem_added_enabled = j_enabled.skills_meta.get('semantic_added') if j_enabled.skills_meta else []
    # Run disabled (reset extracted to simulate fresh)
    j_enabled.skills_extracted = []
    db.upsert_jobs([j_enabled])
    count2 = score_all(db, resume, seed, semantic_override=False)
    assert count2 == 1
    j_disabled = db.fetch_by_id('s1')
    sem_added_disabled = j_disabled.skills_meta.get('semantic_added') if j_disabled.skills_meta else []
    # When disabled, semantic_added should be empty whereas enabled path may have entries (or at least different)
    if sem_added_enabled:  # only assert stronger if model present
        assert not sem_added_disabled
    else:
        # Model may be missing in test env; assert no crash and disabled yields same or fewer
        assert len(sem_added_disabled) <= len(sem_added_enabled)


def test_env_var_disables(tmp_path, monkeypatch):
    db = JobDB(tmp_path/'db.sqlite')
    job = make_job('We build scalable systems and perform advanced analytics on data sets.')
    db.upsert_jobs([job])
    seed = tmp_path/'skills.txt'
    seed.write_text('scalable systems\nadvanced analytics\n', encoding='utf-8')
    resume = tmp_path/'resume.pdf'
    resume.write_bytes(b"%PDF-1.3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF")
    # Set explicit disable env and ensure override None
    monkeypatch.setenv('SCRAPER_NO_SEMANTIC','1')
    count = score_all(db, resume, seed)
    assert count == 1
    j = db.fetch_by_id('s1')
    sem_added = j.skills_meta.get('semantic_added') if j.skills_meta else []
    # Should be empty when disabled via env regardless of model presence
    assert not sem_added
