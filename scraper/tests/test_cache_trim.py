from scraper.jobminer.skill_profile_cache import save_skill_entry, purge_old, _skills_cache_path
from scraper.jobminer import skill_profile_cache
import os, json

def test_cache_trim_respects_entry_limit(tmp_path, monkeypatch):
    # point cache to temp dir by monkeypatching _cache_dir
    monkeypatch.setenv('SCRAPER_SKILL_CACHE_MAX_ENTRIES', '10')
    monkeypatch.setenv('SCRAPER_SKILL_CACHE_MAX_MB', '5')
    # override module cache dir function
    def _tmp_cache_dir():
        d = tmp_path
        d.mkdir(parents=True, exist_ok=True)
        return d
    skill_profile_cache._cache_dir = _tmp_cache_dir  # type: ignore
    # create > limit entries
    for i in range(25):
        desc = f"Sample description number {i} with Python SQL"
        save_skill_entry(desc, ["Python","SQL"], {"i": i})
    path = _skills_cache_path()
    assert path.exists()
    before = len([l for l in path.read_text(encoding='utf-8').splitlines() if l.strip()])
    assert before >= 25
    purge_old()  # uses env-configured limit
    after_lines = [l for l in path.read_text(encoding='utf-8').splitlines() if l.strip()]
    assert len(after_lines) <= 10
    # ensure JSON structure still valid
    for ln in after_lines:
        obj = json.loads(ln)
        assert 'skills' in obj and 'meta' in obj