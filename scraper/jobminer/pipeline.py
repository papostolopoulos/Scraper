from __future__ import annotations
from pathlib import Path
import yaml
from .db import JobDB
from .models import JobPosting
from .resume import load_or_build_resume_profile
from .skills import load_seed_skills, extract_skills, extract_resume_overlap_skills
from .skill_profile_cache import load_skill_entry, save_skill_entry, purge_old, clear_skills_cache, should_clear_env_flag
from .benefits import extract_benefits
from .scoring import aggregate_score
from .weights import load_weights
from .history import append_history
from .anomaly import detect_anomalies
from .semantic_toggle import semantic_enabled
import os, threading, concurrent.futures, math
from .responsibility_match import compute_overlap, compute_semantic_matches, infer_additional_skills
import yaml
import logging
import json, time
from .settings import SETTINGS

CONFIG_DIR = Path(__file__).resolve().parent.parent / 'config'


logger = logging.getLogger(__name__)


def score_all(db: JobDB, resume_pdf: Path, seed_skills_path: Path, target_seniority=None, write_summary: bool = True, semantic_override: bool | None = None, max_workers: int | None = None):
    if target_seniority is None:
        target_seniority = ['Associate','Mid-Senior']
    t_start = time.time()
    seed_skills = load_seed_skills(seed_skills_path)
    t_resume_start = time.time()
    profile = load_or_build_resume_profile(resume_pdf, seed_skills)
    t_resume_end = time.time()
    logger.info(
        "Loaded resume profile",
        extra={
            'total_skills': len(profile.skills),
            'expertise': len(profile.expertise),
            'technical': len(profile.technical),
            'responsibilities': len(profile.responsibilities),
        }
    )
    weights, thresholds = load_weights()
    # load matching thresholds if present
    match_cfg_file = CONFIG_DIR / 'matching.yml'
    match_cfg = {}
    if match_cfg_file.exists():
        try:
            match_cfg = yaml.safe_load(match_cfg_file.read_text(encoding='utf-8')) or {}
        except Exception:
            match_cfg = {}
    ov_cfg = match_cfg.get('overlap', {})
    sem_cfg = match_cfg.get('semantic', {})
    use_semantic = semantic_enabled(match_cfg, semantic_override)
    jobs = db.fetch_all()
    t_fetch_jobs = time.time()
    # In-memory cache: description_hash -> {benefits, extracted, overlap, overlaps_meta} (fast within run)
    skill_cache = {}
    use_disk_cache = True
    if should_clear_env_flag():
        clear_skills_cache()
        logger.info("skill_cache_cleared_env_flag")
    cache_hits = 0
    cache_misses = 0
    t_scoring_start = time.time()
    # Determine max workers (env var fallback)
    if max_workers is None:
        env_workers = os.getenv('SCRAPER_MAX_WORKERS')
        if env_workers and env_workers.isdigit():
            max_workers = int(env_workers)
        else:
            max_workers = 1
    max_workers = max(1, max_workers)

    cache_lock = threading.Lock()

    def process_job(job: JobPosting):
        nonlocal cache_hits, cache_misses
        try:
            desc = job.description_clean
            desc_hash = None
            if desc:
                import hashlib
                desc_hash = hashlib.sha1(desc.encode('utf-8')).hexdigest()
            with cache_lock:
                cached = skill_cache.get(desc_hash) if desc_hash else None
            if desc and not job.benefits:
                if cached and cached.get('benefits') is not None:
                    job.benefits = cached['benefits']
                else:
                    bens = extract_benefits(desc)
                    job.benefits = bens
                    if desc_hash:
                        with cache_lock:
                            skill_cache.setdefault(desc_hash, {})['benefits'] = bens
            if desc:
                if cached and 'overlap' in cached and 'extracted' in cached:
                    overlap = cached['overlap']
                    extracted = cached['extracted']
                else:
                    disk_entry = load_skill_entry(desc) if use_disk_cache else None
                    if disk_entry:
                        overlap = disk_entry.get('meta', {}).get('resume_overlap', [])
                        extracted = disk_entry.get('meta', {}).get('base_extracted', [])
                        with cache_lock:
                            cache_hits += 1
                    else:
                        overlap = extract_resume_overlap_skills(desc, profile.skills)
                        extracted = extract_skills(desc, seed_skills)
                        with cache_lock:
                            cache_misses += 1
                    if desc_hash:
                        with cache_lock:
                            d = skill_cache.setdefault(desc_hash, {})
                            d['overlap'] = overlap
                            d['extracted'] = extracted
                merged = []
                seen = set()
                for lst in (overlap, extracted):
                    for sk in lst:
                        if sk not in seen:
                            seen.add(sk)
                            merged.append(sk)
                meta = {'base_extracted': extracted, 'resume_overlap': overlap, 'overlap_added': [], 'semantic_added': []}
                if profile.responsibilities:
                    if cached and 'resp_overlaps' in cached:
                        resp_overlaps = cached['resp_overlaps']
                    else:
                        resp_overlaps = compute_overlap(
                            profile.responsibilities,
                            desc,
                            min_coverage=ov_cfg.get('min_coverage',0.4),
                            min_fuzzy=ov_cfg.get('min_fuzzy',82)
                        )
                        if desc_hash:
                            with cache_lock:
                                skill_cache.setdefault(desc_hash, {})['resp_overlaps'] = resp_overlaps
                    for ro in resp_overlaps:
                        if ro.best_sentence:
                            sent_low = ro.best_sentence.lower()
                            for sk in seed_skills:
                                if sk.lower() in sent_low and sk not in seen:
                                    seen.add(sk)
                                    merged.append(sk)
                                    meta['overlap_added'].append({'skill': sk, 'coverage': ro.coverage, 'fuzzy': ro.fuzzy})
                    if len(merged) < 5 and use_semantic:
                        if cached and 'sem_matches' in cached:
                            sem_matches = cached['sem_matches']
                        else:
                            sem_matches = compute_semantic_matches(
                                profile.responsibilities,
                                desc,
                                min_similarity=sem_cfg.get('min_similarity',0.64)
                            )
                            if desc_hash:
                                with cache_lock:
                                    skill_cache.setdefault(desc_hash, {})['sem_matches'] = sem_matches
                        inferred = infer_additional_skills(sem_matches, seed_skills)
                        for sk in inferred:
                            if sk not in seen:
                                seen.add(sk)
                                merged.append(sk)
                                meta['semantic_added'].append({'skill': sk})
                job.skills_extracted = merged
                job.skills_meta = meta
                if use_disk_cache and not (cached and 'overlap' in cached):
                    try:
                        save_skill_entry(desc, merged, meta)
                    except Exception:
                        pass
                if merged:
                    logger.info("skills_extracted", extra={'job_id': job.job_id, 'count': len(merged)})
                else:
                    logger.info("no_skills_found", extra={'job_id': job.job_id, 'desc_len': len(job.description_clean)})
            aggregate_score(job, profile.skills, profile.summary, weights, target_seniority)
            if job.score_total is not None and job.score_total >= thresholds['shortlist'] and job.status == 'new':
                job.status = 'shortlisted'
            return job
        except Exception as e:
            logger.error("job_process_error", extra={'job_id': job.job_id, 'error': str(e)})
            return job

    if max_workers == 1 or len(jobs) <= 1:
        for j in jobs:
            updated = process_job(j)
            db.update_scores(updated)
    else:
        # Bound workers to job count
        workers = min(max_workers, len(jobs))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            for updated in ex.map(process_job, jobs, chunksize=1):
                db.update_scores(updated)
    if use_disk_cache:
        purge_old()
        logger.info("skill_cache_stats", extra={'hits': cache_hits, 'misses': cache_misses})
    t_scoring_end = time.time()
    total = time.time() - t_start
    if write_summary:
        # compute additional metrics
        scores = [j.score_total for j in jobs if j.score_total is not None]
        avg_score = round(sum(scores)/len(scores),4) if scores else None
        skills_counts = [len(j.skills_extracted) for j in jobs if j.skills_extracted]
        skills_per_job = round(sum(skills_counts)/len(skills_counts),2) if skills_counts else None
        summary = {
            'jobs_processed': len(jobs),
            'skill_cache_hits': cache_hits,
            'skill_cache_misses': cache_misses,
            'avg_score': avg_score,
            'skills_per_job': skills_per_job,
            'timings': {
                'resume_load_s': round(t_resume_end - t_resume_start, 4),
                'fetch_jobs_s': round(t_scoring_start - t_fetch_jobs, 4),
                'scoring_s': round(t_scoring_end - t_scoring_start, 4),
                'total_s': round(total, 4),
            },
            'parallel_workers': max_workers,
            'parallel_enabled': max_workers > 1
        }
        try:
            SETTINGS.metrics_output_path.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS.metrics_output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            pass
        # Append to historical JSONL
        history_path = Path('scraper/data/exports/run_history.jsonl')
        append_history(summary, history_path)
        try:
            warnings = detect_anomalies(history_path)
            for w in warnings:
                logger.warning("anomaly_detected", extra={'detail': w})
        except Exception:
            pass
    return len(jobs)


def import_mock_json(db: JobDB, json_file: Path):
    data = json.loads(json_file.read_text(encoding='utf-8'))
    jobs = []
    for item in data:
        jobs.append(JobPosting(**item))
    db.upsert_jobs(jobs)
    return len(jobs)
