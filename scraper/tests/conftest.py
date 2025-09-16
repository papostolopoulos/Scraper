"""Global pytest fixtures & test speed optimizations.
 - Forces fast mode by stubbing heavy PDF reads.
 - Sets env vars to disable logging side effects.
 - Provides a lightweight resume sample for scoring pipeline tests.
"""
from __future__ import annotations
import os
import pytest


@pytest.fixture(autouse=True, scope="session")
def test_env_setup():
    os.environ.setdefault('SCRAPER_DISABLE_FILE_LOGS', '1')
    os.environ.setdefault('SCRAPER_DISABLE_EVENTS', '1')
    os.environ.setdefault('SCRAPER_POLITE_MIN', '0.01')
    os.environ.setdefault('SCRAPER_POLITE_MAX', '0.02')
    os.environ.setdefault('SCRAPER_FAST_TEST', '1')
    yield
    # teardown not required


@pytest.fixture(autouse=True, scope="session")
def stub_pdf_reader():
    patched = False
    original = None
    if os.getenv('SCRAPER_FAST_TEST'):
        from scraper.jobminer import resume as resume_mod
        original = getattr(resume_mod, 'extract_text', None)
        def _fast_extract_text(pdf_path):
            return (
                "PROFESSIONAL SUMMARY\nSeasoned Data Engineer with Python, SQL, ETL expertise.\n"
                "AREAS OF EXPERTISE\nData Pipelines | Orchestration | Cloud | APIs | Testing\n"
                "TECHNICAL SKILLS\nPython, SQL, Airflow, Docker, Kubernetes, ETL\n"
                "WORK EXPERIENCE\nLed data platform migration improving performance.\nBuilt scalable ingestion pipelines reducing latency.\n"
            )
        resume_mod.extract_text = _fast_extract_text  # type: ignore
        patched = True
    yield
    if patched and original is not None:
        from scraper.jobminer import resume as resume_mod
        resume_mod.extract_text = original  # type: ignore
import sys, pathlib
# Add project root and scraper package parent to sys.path for tests
ROOT = pathlib.Path(__file__).resolve().parents[2]  # points to project root
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT / 'scraper'))
    sys.path.insert(0, str(ROOT))
