from __future__ import annotations
"""Retro-enrich existing job rows: company_name from page_title pipe pattern, work_mode/employment_type/seniority & skills.
Run after improving extraction heuristics to backfill older records.
"""
import sys, re
from pathlib import Path
from jobminer.db import JobDB
from jobminer.skills import load_seed_skills, extract_skills
from jobminer.benefits import extract_benefits
from jobminer.resume import build_resume_profile
from jobminer.models import JobPosting

EMPLOYMENT_TYPE_RGX = re.compile(r"\b(full[- ]?time|part[- ]?time|contract|temporary|internship|apprenticeship|freelance|consultant|seasonal)\b", re.I)
WORK_MODE_PATTERNS = [
    (re.compile(r"\b(remote-first|remote)\b", re.I), 'remote'),
    (re.compile(r"\b(hybrid)\b", re.I), 'hybrid'),
    (re.compile(r"\b(on[- ]?site|onsite)\b", re.I), 'onsite'),
]
SENIORITY_RGX = re.compile(r"\b(intern|graduate|junior|entry|associate|mid|senior|sr\.?|staff|principal|lead|director|vp|vice president|chief|cxo|cto|ceo|head)\b", re.I)
SENIORITY_MAP = {
    'intern':'intern','graduate':'entry','junior':'entry','entry':'entry','associate':'associate','mid':'mid','senior':'senior','sr.':'senior','sr':'senior','staff':'staff','principal':'principal','lead':'lead','director':'director','vp':'vp','vice president':'vp','chief':'cxo','cxo':'cxo','cto':'cxo','ceo':'cxo','head':'director'
}

def derive_company_from_page_title(page_title: str) -> str | None:
    if not page_title or '|' not in page_title:
        return None
    parts = [p.strip() for p in page_title.split('|') if p.strip()]
    if len(parts) >= 2:
        cand = parts[1]
        if cand.lower() not in {'linkedin','home'} and 1 <= len(cand.split()) <= 6:
            return cand
    return None

def retro_enrich(db: JobDB, resume_pdf: Path, seed_skills_path: Path):
    seed_skills = load_seed_skills(seed_skills_path)
    profile = build_resume_profile(resume_pdf, seed_skills)
    jobs = db.fetch_all()
    updated = 0
    for job in jobs:
        changed = False
        # Company from page_title
        if job.company_name == 'Unknown' and job.page_title:
            comp = derive_company_from_page_title(job.page_title)
            if comp:
                job.company_name = comp
                changed = True
        blob = ' '.join(filter(None, [job.title, job.description_clean])) if (job.title or job.description_clean) else ''
        if blob:
            if not job.employment_type:
                m = EMPLOYMENT_TYPE_RGX.search(blob)
                if m:
                    job.employment_type = m.group(1).lower().replace(' ', '-')
                    changed = True
            if not job.work_mode:
                for rgx, label in WORK_MODE_PATTERNS:
                    if rgx.search(blob):
                        job.work_mode = label
                        changed = True
                        break
            if not job.seniority_level:
                sm = SENIORITY_RGX.search(blob)
                if sm:
                    job.seniority_level = SENIORITY_MAP.get(sm.group(1).lower(), sm.group(1).lower())
                    changed = True
        if not job.benefits and job.description_clean:
            b = extract_benefits(job.description_clean)
            if b:
                job.benefits = b
                changed = True
        if job.description_clean:
            job.skills_extracted = extract_skills(job.description_clean, profile.skills)
            if job.skills_extracted:
                changed = True
        if changed:
            # Upsert single
            db.upsert_jobs([job])
            updated += 1
    return updated, len(jobs)

if __name__ == '__main__':
    db = JobDB()
    resume_pdf = Path('resume.pdf')
    seed = Path('scraper/config/seed_skills.txt')
    upd, total = retro_enrich(db, resume_pdf, seed)
    print(f"Retro-enriched {upd} of {total} jobs")