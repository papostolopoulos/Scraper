from pathlib import Path
import sys

PARENT = Path(__file__).resolve().parent.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from jobminer.db import JobDB
from jobminer.pipeline import import_mock_json, score_all
from jobminer.exporter import Exporter

if __name__ == '__main__':
    base = Path(__file__).resolve().parent.parent
    db = JobDB()
    mock_file = base / 'data' / 'mock_jobs.json'
    if mock_file.exists():
        import_mock_json(db, mock_file)
    resume_pdf = base.parent / 'Resume - Paris_Apostolopoulos.pdf'
    seed_skills = base / 'config' / 'skills_seed.txt'
    if resume_pdf.exists():
        score_all(db, resume_pdf, seed_skills)
    exporter = Exporter(db, base / 'data' / 'exports')
    exporter.export_all()
    print('Pipeline complete.')
