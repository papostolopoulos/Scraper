import pytest
from pathlib import Path
from scraper.jobminer.db import JobDB
import warnings

@pytest.fixture()
def jobdb(tmp_path: Path):
    db = JobDB(tmp_path / 'test.sqlite')
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(autouse=True)
def fail_on_resource_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        yield
