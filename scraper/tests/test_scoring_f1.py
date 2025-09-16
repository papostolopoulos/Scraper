from scraper.jobminer.scoring import compute_skill_score

def test_f1_skill_scoring_basic_distribution():
    resume = [f"Skill{i}" for i in range(1, 21)]
    # Job overlaps with first 3 of core (default core_limit=12)
    job_skills = ["Skill1", "Skill2", "Skill3", "ExtraA", "ExtraB"]
    score = compute_skill_score(job_skills, resume)
    # F1 with precision=3/5=0.6, recall=3/12=0.25 -> F1=0.3529; smoothing exponent 0.92 ~ 0.36
    assert 0.32 < score < 0.40, score

def test_f1_skill_scoring_no_overlap():
    assert compute_skill_score(["X"], ["A","B"]) == 0.0
