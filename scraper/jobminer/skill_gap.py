"""Skill gap aggregation.

Computes the most frequently required skills across shortlisted jobs that are
NOT already present on the resume skill list. This is a lightweight heuristic
intended to surface common missing capabilities for up-skilling decisions.

Returned metrics per skill:
    skill: normalized skill token
    count: number of shortlisted jobs containing the skill
    shortlist_pct: count / total_shortlisted (float)

Heuristics:
- Case insensitive (all lowered)
- Filters out skills shorter than 2 chars, purely numeric tokens, and those in an optional stop list
- Simple frequency threshold (min_freq) to reduce noise
"""
from __future__ import annotations
from typing import Iterable, List, Dict, Set, Optional
from pathlib import Path
import os
import yaml

DEFAULT_STOP = { 'and', 'or', 'sql', 'the', 'with', 'for' }  # keep 'sql' optional? treat as usually already on resume but we will still include unless resume has it.

def _load_taxonomy(explicit_path: Optional[Path] = None) -> Dict[str,str]:
    """Load skill -> category taxonomy mapping (lowercased keys)."""
    paths: List[Path] = []
    if explicit_path:
        paths.append(explicit_path)
    paths.append(Path(__file__).resolve().parent.parent / 'config' / 'skill_taxonomy.yml')
    for p in paths:
        try:
            if p.exists():
                with open(p, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                    return {str(k).strip().lower(): str(v).strip() for k,v in data.items() if k and v}
        except Exception:
            continue
    return {}

def _load_category_weights(explicit_path: Optional[Path] = None) -> Dict[str,float]:
    """Load category -> weight mapping (floats)."""
    paths: List[Path] = []
    if explicit_path:
        paths.append(explicit_path)
    paths.append(Path(__file__).resolve().parent.parent / 'config' / 'skill_category_weights.yml')
    for p in paths:
        try:
            if p.exists():
                with open(p, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                    out: Dict[str,float] = {}
                    for k,v in data.items():
                        try:
                            out[str(k).strip()] = float(v)
                        except Exception:
                            continue
                    return out
        except Exception:
            continue
    return {}

def compute_skill_gaps(
    shortlisted_jobs: Iterable,
    resume_skills: Iterable[str],
    *,
    min_freq: int = 2,
    top_n: int = 30,
    stop: Set[str] | None = None,
    taxonomy_path: Optional[str] = None,
    category_weights_path: Optional[str] = None,
    include_priority: bool = True,
) -> List[Dict]:
    resume_set = {s.strip().lower() for s in resume_skills if s and s.strip()}
    stop_set = {s.lower() for s in (stop or set())}
    counts: Dict[str,int] = {}
    jobs_list = list(shortlisted_jobs)
    if not jobs_list:
        return []
    for job in jobs_list:
        skills = getattr(job, 'skills_extracted', []) or []
        seen: Set[str] = set()
        for raw in skills:
            if not raw:
                continue
            s = raw.strip().lower()
            if len(s) < 2:
                continue
            if s.isnumeric():
                continue
            if s in resume_set:
                continue
            if s in stop_set:
                continue
            if s in seen:  # de-duplicate within a single job
                continue
            seen.add(s)
            counts[s] = counts.get(s, 0) + 1
    total = len(jobs_list)
    # Apply min freq filter
    items = [ (skill, c) for skill, c in counts.items() if c >= min_freq ]
    # sort by (count desc, skill asc) for determinism
    items.sort(key=lambda x: (-x[1], x[0]))
    taxonomy = _load_taxonomy(Path(taxonomy_path)) if taxonomy_path else _load_taxonomy()
    cat_weights = _load_category_weights(Path(category_weights_path)) if category_weights_path else (_load_category_weights() if include_priority else {})
    # Pre-compute avg shortlisted job score (non-null) to scale
    non_null_scores = [getattr(j, 'score_total', None) for j in jobs_list if getattr(j, 'score_total', None) is not None]
    avg_job_score = sum(non_null_scores)/len(non_null_scores) if non_null_scores else 1.0
    results = []
    for skill, c in items[:top_n]:
        entry = {
            'skill': skill,
            'count': c,
            'shortlist_pct': round(c / total, 4)
        }
        cat = taxonomy.get(skill.lower())
        if cat:
            entry['category'] = cat
        if include_priority:
            # Base frequency factor = shortlist_pct
            freq_factor = entry['shortlist_pct']
            cat_weight = cat_weights.get(cat, 1.0) if cat_weights else 1.0
            entry['priority_score'] = round(freq_factor * cat_weight * avg_job_score, 5)
        results.append(entry)
    if include_priority:
        results.sort(key=lambda x: (-x.get('priority_score', 0), -x['count'], x['skill']))
    return results

__all__ = ['compute_skill_gaps']
