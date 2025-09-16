import datetime as dt
from scraper.jobminer.dedupe import detect_duplicates, build_signature
from scraper.jobminer.models import JobPosting
from scraper.jobminer.anomaly import detect_anomalies
from scraper.jobminer.redaction import load_redaction_config, redact_text
from scraper.jobminer.compliance import automation_allowed
from pathlib import Path


def make_job(i, title='Engineer', comp='Acme', loc='Remote', desc='We build systems'):
    return JobPosting(
        job_id=str(i),
        title=title,
        company_name=comp,
        location=loc,
        work_mode='remote',
        collected_at=dt.datetime.utcnow(),
        description_raw=desc,
        description_clean=desc,
        employment_type='Full-time',
        seniority_level='Mid',
        skills_extracted=[],
        recruiter_profiles=[],
        benefits=[],
        status='new'
    )


def test_dedupe_similarity_disabled():
    jobs = [make_job(1), make_job(2)]
    # Force identical signature by same title/desc
    count = detect_duplicates(jobs, desc_prefix=0, enable_similarity=False)
    assert count == 1


def test_dedupe_similarity_enabled_threshold_not_met():
    # Different descriptions keep Jaccard below threshold
    jobs = [make_job(1, desc='alpha beta gamma'), make_job(2, desc='alpha delta epsilon')]
    count = detect_duplicates(jobs, desc_prefix=0, enable_similarity=True, jaccard_min=0.9)
    assert count == 0  # deterministic pass keeps both distinct because titles/diffs


def test_anomaly_no_warnings(tmp_path):
    hist = tmp_path / 'hist.jsonl'
    # Create 6 runs where last is similar to baseline
    entries = []
    for i in range(6):
        entries.append({'avg_score': 0.70 + (i*0.005), 'skills_per_job': 5.0 + (i*0.1)})
    hist.write_text('\n'.join(__import__('json').dumps(e) for e in entries), encoding='utf-8')
    warnings = detect_anomalies(hist, recent_n=5, drop_threshold_pct=0.35)
    assert warnings == []


def test_redaction_disabled(tmp_path, monkeypatch):
    # Env disables even if config default enables
    monkeypatch.setenv('SCRAPER_REDACT_EXPORT', '0')
    cfg = load_redaction_config(tmp_path)
    text = 'Email me at test@example.com'
    assert redact_text(text, cfg) == text


def test_compliance_default_deny(tmp_path):
    assert automation_allowed(tmp_path) is False  # no file, no env, no flag
