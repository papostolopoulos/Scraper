from pathlib import Path
import sys

PARENT = Path(__file__).resolve().parent.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from jobminer.db import JobDB
from jobminer.pipeline import score_all
import argparse

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--resume', default='Resume - Paris_Apostolopoulos.pdf')
    parser.add_argument('--seed', default='config/seed_skills.txt')
    parser.add_argument('--no-semantic', action='store_true', help='Disable semantic mapping layer')
    args = parser.parse_args()
    base = Path(__file__).resolve().parent.parent
    resume_pdf = base.parent / args.resume
    seed_skills = base / args.seed
    if not resume_pdf.exists():
        raise SystemExit(f"Resume PDF not found at {resume_pdf}")
    # quick toggle of semantic via matching.yml override
    if args.no_semantic:
        cfg_file = base / 'config' / 'matching.yml'
        if cfg_file.exists():
            import yaml
            cfg = yaml.safe_load(cfg_file.read_text(encoding='utf-8')) or {}
            cfg.setdefault('semantic', {})['enable'] = False
            cfg_file.write_text(yaml.safe_dump(cfg), encoding='utf-8')
    db = JobDB()
    count = score_all(db, resume_pdf, seed_skills)
    print(f"Scored {count} jobs")
