"""Utility to trim the on-disk skills cache respecting configured limits.
Usage (PowerShell):
  python -m scraper.scripts.trim_skill_cache
Optional env vars:
  SCRAPER_SKILL_CACHE_MAX_ENTRIES (default 500)
  SCRAPER_SKILL_CACHE_MAX_MB (default 8)
"""
from __future__ import annotations
from scraper.jobminer.skill_profile_cache import purge_old, _skills_cache_path
from scraper.jobminer.settings import SETTINGS
import os

def main():
    path = _skills_cache_path()
    before = 0
    if path.exists():
        before = sum(1 for _ in path.read_text(encoding='utf-8').splitlines() if _.strip())
    purge_old()  # uses SETTINGS limits
    after = 0
    size = 0
    if path.exists():
        lines = [l for l in path.read_text(encoding='utf-8').splitlines() if l.strip()]
        after = len(lines)
        size = path.stat().st_size
    print(f"Trimmed skills cache: entries {before} -> {after}; size={size} bytes; max_entries={SETTINGS.skill_cache_max_entries} max_mb={SETTINGS.skill_cache_max_disk_mb}")

if __name__ == '__main__':
    main()
