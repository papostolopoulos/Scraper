from pathlib import Path
import sys

PARENT = Path(__file__).resolve().parent.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from jobminer.db import JobDB
from jobminer.pipeline import import_mock_json

if __name__ == '__main__':
    base = Path(__file__).resolve().parent.parent
    mock_file = base / 'data' / 'mock_jobs.json'
    if not mock_file.exists():
        sample = [
            {
                "job_id": "m1",
                "title": "Data Analyst",
                "company_name": "Acme Analytics",
                "location": "Remote - US",
                "skills_extracted": ["sql","python","power bi"],
                "description_raw": "Analyze data and build Power BI dashboards. 401k and health insurance included.",
                "description_clean": "Analyze data and build Power BI dashboards. 401k and health insurance included.",
                "seniority_level": "Associate",
                "offered_salary_min": 80000,
                "offered_salary_max": 95000,
                "offered_salary_currency": "USD",
                "benefits": ["401k","health insurance"],
                "apply_url": "https://example.com/apply"
            },
            {
                "job_id": "m2",
                "title": "Business Intelligence Analyst",
                "company_name": "DataWave",
                "location": "New York, NY (Hybrid)",
                "skills_extracted": ["sql","tableau","etl"],
                "description_raw": "Support ETL pipelines, Tableau reporting, bonus eligible, stock options.",
                "description_clean": "Support ETL pipelines, Tableau reporting, bonus eligible, stock options.",
                "seniority_level": "Mid-Senior",
                "offered_salary_min": 100000,
                "offered_salary_max": 120000,
                "offered_salary_currency": "USD",
                "benefits": ["bonus","stock"],
                "apply_url": "https://example.com/apply2"
            }
        ]
        import json
        mock_file.write_text(json.dumps(sample, indent=2), encoding='utf-8')
    db = JobDB()
    inserted = import_mock_json(db, mock_file)
    print(f"Inserted {inserted} mock jobs")
