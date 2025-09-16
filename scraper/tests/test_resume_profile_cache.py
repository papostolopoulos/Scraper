import time
import pytest
from pathlib import Path
from scraper.jobminer.resume import (
    load_or_build_resume_profile,
    get_resume_profile_cache_path,
)
from scraper.jobminer.skills import load_seed_skills


@pytest.mark.slow
def test_resume_profile_caching(tmp_path: Path):
    # Copy resume PDF into tmp to avoid polluting original hash scenario
    root = Path(__file__).resolve().parents[2]
    pdf_src = next((p for p in root.iterdir() if p.name.lower().startswith('resume') and p.suffix.lower()=='.pdf'), None)
    assert pdf_src, 'Resume PDF not found in project root for test'
    pdf_copy = tmp_path / 'resume_copy.pdf'
    pdf_copy.write_bytes(pdf_src.read_bytes())
    seed_file = tmp_path / 'skills.txt'
    seed_file.write_text('Python\nSQL\nData\nLeadership', encoding='utf-8')
    seeds = load_seed_skills(seed_file)

    # Ensure no cache (different location)
    cache_path = get_resume_profile_cache_path()
    if cache_path.exists():
        cache_path.unlink()

    prof1 = load_or_build_resume_profile(pdf_copy, seeds, force_rebuild=False)
    assert prof1.skills, 'Expected aggregated skills'
    t1 = cache_path.stat().st_mtime
    # Second load should hit cache (no rebuild) and be very fast
    start = time.time()
    prof2 = load_or_build_resume_profile(pdf_copy, seeds, force_rebuild=False)
    elapsed = time.time() - start
    assert prof2.skills == prof1.skills
    # verify cache file not rewritten (mtime stable)
    assert cache_path.stat().st_mtime == t1, 'Cache unexpectedly rewritten'
    # Allow modest overhead (Windows FS + PDF hash stat); target <120ms
    assert elapsed < 0.12, f'Cached load too slow: {elapsed:.3f}s'

    # Force rebuild should change mtime (allow small delay)
    time.sleep(0.01)
    prof3 = load_or_build_resume_profile(pdf_copy, seeds, force_rebuild=True)
    t2 = cache_path.stat().st_mtime
    assert t2 > t1, 'Cache not updated after force rebuild'
    assert prof3.skills == prof1.skills

    # Modify seed list (add new skill); expect rebuild
    time.sleep(0.01)
    seed_file.write_text('Python\nSQL\nData\nLeadership\nKubernetes', encoding='utf-8')
    seeds2 = load_seed_skills(seed_file)
    t_before_seed = cache_path.stat().st_mtime
    prof4 = load_or_build_resume_profile(pdf_copy, seeds2, force_rebuild=False)
    t_after_seed = cache_path.stat().st_mtime
    # New cache hash triggers rewrite (mtime increases)
    assert t_after_seed > t_before_seed, 'Cache not rebuilt after seed change'
    assert prof4.skills, 'Expected skills after seed change rebuild'

    # Cleanup
    if cache_path.exists():
        try:
            cache_path.unlink()
        except Exception:
            pass
