import os, time, sys, pytest

@pytest.mark.slow
def test_collector_import_speed():
    os.environ['SCRAPER_DISABLE_FILE_LOGS'] = '1'
    os.environ['SCRAPER_DISABLE_EVENTS'] = '1'
    start = time.time()
    __import__('scraper.jobminer.collector')
    elapsed = time.time() - start
    assert elapsed < 0.35, f"collector import too slow: {elapsed:.3f}s"

def test_skills_lazy_rapidfuzz():
    # Ensure rapidfuzz not pre-imported
    if 'rapidfuzz' in sys.modules:
        del sys.modules['rapidfuzz']
    start = time.time()
    from scraper.jobminer import skills  # noqa: F401
    t_no_use = time.time() - start
    assert 'rapidfuzz' not in sys.modules, 'rapidfuzz loaded prematurely'
    # Now call function that triggers rapidfuzz
    from scraper.jobminer.skills import extract_resume_overlap_skills
    _ = extract_resume_overlap_skills('python sql data', ['Python', 'Scala'], 0.6)
    assert 'rapidfuzz' in sys.modules, 'rapidfuzz not loaded after fuzzy function call'
    # Basic sanity: initial import should be fast
    assert t_no_use < 0.15, f"skills base import slow: {t_no_use:.3f}s"
