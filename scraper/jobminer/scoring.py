from __future__ import annotations
from typing import List, Dict
from datetime import datetime, timezone
from math import exp
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


def compute_skill_score(job_skills: List[str], resume_skills: List[str], core_limit: int = 12) -> float:
    """Compute a more discriminative skill score using F1 (precision/recall) against a core subset of resume skills.

    - precision = overlap / len(job_skills)
    - recall    = overlap / len(core_resume)
    - F1        = 2 * p * r / (p + r)

    core_limit limits dilution when resume has many skills.
    Returns 0.0 if no overlap.
    """
    if not job_skills or not resume_skills:
        return 0.0
    core_resume = [s.lower() for s in resume_skills[:core_limit]]
    job_norm = [s.lower() for s in job_skills]
    overlap = set(job_norm) & set(core_resume)
    if not overlap:
        return 0.0
    precision = len(overlap) / max(len(job_norm), 1)
    recall = len(overlap) / max(len(core_resume), 1)
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) else 0.0
    # Mild smoothing boost to differentiate low counts
    return round(min(1.0, f1 ** 0.92), 6)


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
    skill_score = compute_skill_score(job.skills_extracted, resume_skills)
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

    breakdown = {
        'skill': skill_score,
        'semantic': semantic_score,
        'recency': recency_score,
        'seniority_component': 1 - seniority_penalty,
        'company': company_component
    }
    job.score_total = round(total, 4)
    job.score_breakdown = breakdown
    return job
