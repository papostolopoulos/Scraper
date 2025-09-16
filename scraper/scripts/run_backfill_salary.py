from jobminer.db import JobDB
from jobminer.collector import extract_salary

def backfill():
    db = JobDB()
    jobs = db.fetch_all()
    updated = 0
    for j in jobs:
        # Skip if we already have at least a min salary recorded
        if j.offered_salary_min is not None:
            continue
        if not j.description_raw:
            continue
        min_a, max_a, cur, period, raw = extract_salary(j.description_raw)
        if min_a is not None:
            j.offered_salary_min = min_a
            j.offered_salary_max = max_a
            if cur:
                j.offered_salary_currency = cur
            # period/raw deprecated; ignored
            try:
                # Remove attributes if lingering from older instances
                if hasattr(j, 'offered_salary_period'):
                    delattr(j, 'offered_salary_period')
                if hasattr(j, 'offered_salary_raw'):
                    delattr(j, 'offered_salary_raw')
            except Exception:
                pass
            db.upsert_jobs([j])
            updated += 1
    print(f"Backfilled {updated} jobs with salary info.")

if __name__ == '__main__':
    backfill()
