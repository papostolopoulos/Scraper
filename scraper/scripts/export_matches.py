from pathlib import Path
import sys
from datetime import datetime

PARENT = Path(__file__).resolve().parent.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from jobminer.db import JobDB
from jobminer.resume import build_resume_profile
from jobminer.skills import load_seed_skills
from jobminer.responsibility_match import compute_overlap, compute_semantic_matches

def main():
    base = Path(__file__).resolve().parent.parent
    resume_pdf = base.parent / 'Resume - Paris_Apostolopoulos.pdf'
    seed_skills_file = base / 'config' / 'seed_skills.txt'
    out_dir = base / 'exports'
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = build_resume_profile(resume_pdf, load_seed_skills(seed_skills_file))
    db = JobDB()
    rows = []
    for job in db.fetch_all():
        if not job.description_clean:
            continue
        overlaps = compute_overlap(profile.responsibilities, job.description_clean)
        sem = compute_semantic_matches(profile.responsibilities, job.description_clean)
        for o in overlaps:
            rows.append({
                'job_id': job.job_id,
                'company': job.company_name,
                'title': job.title,
                'type': 'overlap',
                'responsibility': o.responsibility,
                'match_sentence': o.best_sentence or '',
                'coverage': o.coverage,
                'fuzzy': o.fuzzy,
                'similarity': ''
            })
        for m in sem:
            rows.append({
                'job_id': job.job_id,
                'company': job.company_name,
                'title': job.title,
                'type': 'semantic',
                'responsibility': m.responsibility,
                'match_sentence': m.job_sentence,
                'coverage': '',
                'fuzzy': '',
                'similarity': round(m.similarity,3)
            })
    import pandas as pd
    if rows:
        df = pd.DataFrame(rows)
        outfile = out_dir / f"responsibility_matches_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        df.to_excel(outfile, index=False)
        print(f"Wrote {len(rows)} match rows to {outfile}")
    else:
        print("No matches produced.")

if __name__ == '__main__':
    main()
