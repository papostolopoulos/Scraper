from __future__ import annotations
from typing import List, Dict, Optional
from datetime import datetime, timezone
from math import exp, log
from .models import JobPosting
from .weights import load_weights

try:
    from sentence_transformers import SentenceTransformer, util
except ImportError:  # graceful fallback if not installed yet
    SentenceTransformer = None
    util = None

EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
_model = None


def get_model():
    global _model
    if _model is None and SentenceTransformer:
        _model = SentenceTransformer(EMBED_MODEL_NAME)
    return _model


def compute_skill_score(
    job_skills: List[str],
    resume_skills: List[str],
    freq_map: Optional[Dict[str, int]] = None,
    total_jobs: int = 1,
    dynamic_core: bool = True,
) -> Dict[str, float]:
    """Weighted skill score with IDF-like weighting and adaptive core set.

    Returns dict containing:
      score, precision, recall, overlap_count, core_size
    """
    if not job_skills or not resume_skills:
        return {"score": 0.0, "precision": 0.0, "recall": 0.0, "overlap_count": 0, "core_size": 0}

    # Determine core resume subset size adaptively: half the resume skills bounded [8,24]
    if dynamic_core:
        core_size = min(24, max(8, int(len(resume_skills) * 0.5)))
    else:
        core_size = min(12, len(resume_skills))
    core_resume = [s.lower() for s in resume_skills[:core_size]]
    job_norm = [s.lower() for s in job_skills]

    # Weighting (IDF-like): w = 1 + log(1 + total_jobs/(1+freq(skill)))
    def weight(skill: str) -> float:
        if not freq_map:
            return 1.0 + (len(skill)/40.0)  # light length-based proxy
        f = freq_map.get(skill.lower(), 0)
        return 1.0 + log(1 + (total_jobs / (1 + f)))

    overlap_set = set(job_norm) & set(core_resume)
    if not overlap_set:
        return {"score": 0.0, "precision": 0.0, "recall": 0.0, "overlap_count": 0, "core_size": core_size}

    job_denom = sum(weight(s) for s in job_norm) or 1.0
    core_denom = sum(weight(s) for s in core_resume) or 1.0
    overlap_weight = sum(weight(s) for s in overlap_set)
    precision = overlap_weight / job_denom
    recall = overlap_weight / core_denom
    if (precision + recall) == 0:
        f1 = 0.0
    else:
        f1 = (2 * precision * recall) / (precision + recall)
    # Small bonus for breadth of overlap relative to core (diminishing)
    breadth_bonus = min(0.08, 0.08 * (overlap_weight / (0.35 * core_denom)))
    score = min(1.0, f1 + breadth_bonus)
    return {
        "score": round(score, 6),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "overlap_count": len(overlap_set),
        "core_size": core_size,
    }


def compute_semantic_score(job: JobPosting, resume_summary: str) -> float:
    if not (resume_summary and job.description_clean):
        return 0.0
    model = get_model()
    if not model:
        # fallback to fuzzy ratio on first 500 chars (lazy import rapidfuzz)
        try:
            from rapidfuzz import fuzz  # type: ignore
            return fuzz.partial_ratio(resume_summary[:500], job.description_clean[:500]) / 100.0
        except Exception:
            return 0.0
    emb_resume = model.encode(resume_summary, convert_to_tensor=True)
    emb_job = model.encode(job.description_clean[:2000], convert_to_tensor=True)
    sim = float(util.cos_sim(emb_resume, emb_job).item())
    return max(0.0, min(1.0, (sim + 1) / 2))  # map [-1,1] -> [0,1]


def compute_recency_score(posted_at, now: datetime) -> float:
    if not posted_at:
        return 0.3  # neutral-ish
    days = (now.date() - posted_at).days
    return exp(-0.25 * days)  # fast decay


def compute_seniority_penalty(job_seniority: str, target_levels: List[str]) -> float:
    if not job_seniority:
        return 0.0
    if job_seniority in target_levels:
        return 0.0
    return 0.25  # simple fixed penalty for mismatch


def aggregate_score(job: JobPosting, resume_skills: List[str], resume_summary: str, weights: Dict[str, float] | None, target_seniority: List[str]):
    if weights is None:
        weights, _ = load_weights()
    now = datetime.now(timezone.utc)
    # NOTE: compute_skill_score is now invoked upstream in score_all where frequency map is available.
    skill_score = job.score_breakdown.get('skill') if job.score_breakdown else None
    if skill_score is None:
        # fallback (should not normally happen)
        tmp = compute_skill_score(job.skills_extracted, resume_skills)
        skill_score = tmp['score']
    semantic_score = compute_semantic_score(job, resume_summary)
    recency_score = compute_recency_score(job.posted_at, now)
    seniority_penalty = compute_seniority_penalty(job.seniority_level, target_seniority)

    # company weight currently unused -> placeholder 0
    company_component = 0.0

    total = (
        weights.get('skill', 0)*skill_score +
        weights.get('semantic', 0)*semantic_score +
        weights.get('recency', 0)*recency_score +
        weights.get('seniority', 0)*(1 - seniority_penalty) +
        weights.get('company', 0)*company_component
    )

    # Preserve existing breakdown entries if pre-populated (skill metrics added earlier)
    base_breakdown = job.score_breakdown or {}
    base_breakdown.update({
        'skill': skill_score,
        'semantic': semantic_score,
        'recency': recency_score,
        'seniority_component': 1 - seniority_penalty,
        'company': company_component
    })
    job.score_total = round(total, 4)
    job.score_breakdown = base_breakdown
    return job
