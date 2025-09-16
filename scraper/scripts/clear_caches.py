from scraper.jobminer.resume import get_resume_profile_cache_path
from scraper.jobminer.skill_profile_cache import clear_skills_cache
from pathlib import Path
import argparse, sys

def clear_resume_cache():
    p = get_resume_profile_cache_path()
    if p.exists():
        try:
            p.unlink()
            print(f"Removed {p}")
        except Exception as e:
            print(f"Failed removing {p}: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Clear resume and skill profile caches")
    parser.add_argument('--resume', action='store_true', help='Clear resume profile cache')
    parser.add_argument('--skills', action='store_true', help='Clear skill description cache')
    args = parser.parse_args()
    if not (args.resume or args.skills):
        args.resume = args.skills = True
    if args.resume:
        clear_resume_cache()
    if args.skills:
        clear_skills_cache()

if __name__ == '__main__':
    main()
