import os, time, pytest
from pathlib import Path
from scraper.jobminer.skill_profile_cache import (
    save_skill_entry, load_skill_entry, clear_skills_cache, _skills_cache_path, _CACHE_VERSION
)


def test_skill_cache_save_and_load(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    clear_skills_cache()
    desc = "Python data engineering ETL orchestration"
    assert load_skill_entry(desc) is None
    merged = ["Python","Data Engineering"]
    meta = {"resume_overlap": ["Python"], "base_extracted": ["Python","Data Engineering"]}
    save_skill_entry(desc, merged, meta)
    hit = load_skill_entry(desc)
    assert hit is not None
    assert hit["skills"] == merged
    assert hit["meta"]["resume_overlap"] == ["Python"]
    # Expire by manipulating timestamp
    path = _skills_cache_path()
    lines = path.read_text(encoding='utf-8').splitlines()
    import json
    obj = json.loads(lines[-1])
    obj["ts"] = 0  # force stale
    lines[-1] = json.dumps(obj)
    path.write_text("\n".join(lines), encoding='utf-8')
    stale = load_skill_entry(desc)
    assert stale is None, 'Expected stale entry ignored'


def test_env_flag_clears_skill_cache(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # ensure clean slate independent of other tests
    clear_skills_cache()
    desc = "Kubernetes platform scaling"
    save_skill_entry(desc, ["Kubernetes"], {"resume_overlap":[], "base_extracted":["Kubernetes"]})
    assert load_skill_entry(desc) is not None
    # Set env flag and import should_clear_env_flag (import at top-level avoids shadowing)
    os.environ['SCRAPER_CLEAR_SKILL_CACHE'] = '1'
    from scraper.jobminer.skill_profile_cache import should_clear_env_flag as _should_clear, clear_skills_cache as _clear
    if _should_clear():
        _clear()
    os.environ.pop('SCRAPER_CLEAR_SKILL_CACHE')
    assert load_skill_entry(desc) is None