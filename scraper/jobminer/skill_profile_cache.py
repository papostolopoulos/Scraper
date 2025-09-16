from __future__ import annotations
"""Disk cache for per-description skill extraction layers.
Stores merged skill list plus meta pieces to avoid recomputation.
Keyed by SHA1 hash of normalized description text.
"""
from pathlib import Path
import json, hashlib, time, os
from typing import Any, Dict
from .settings import SETTINGS

_CACHE_VERSION = 1
_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days default


def _cache_dir() -> Path:
    return Path(__file__).resolve().parent / 'data'

def _skills_cache_path() -> Path:
    return _cache_dir() / 'skills_cache.jsonl'


def _sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode('utf-8')).hexdigest()


def load_skill_entry(desc: str) -> Dict[str, Any] | None:
    """Linear scan JSONL (expected small). Could optimize with index later.
    Honors max-age; expired entries ignored.
    """
    path = _skills_cache_path()
    if not path.exists():
        return None
    h = _sha1_text(desc)
    now = time.time()
    try:
        with path.open('r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get('h') == h and obj.get('v') == _CACHE_VERSION:
                    if now - obj.get('ts', 0) > _MAX_AGE_SECONDS:
                        return None
                    return obj
    except Exception:
        return None
    return None


def save_skill_entry(desc: str, merged: list[str], meta: dict) -> None:
    path = _skills_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        obj = {
            'v': _CACHE_VERSION,
            'h': _sha1_text(desc),
            'ts': time.time(),
            'skills': merged,
            'meta': meta,
        }
        with path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(obj, ensure_ascii=False) + '\n')
    except Exception:
        pass


def _enforce_disk_size(path: Path):
    try:
        if not path.exists():
            return
        max_bytes = SETTINGS.skill_cache_max_disk_mb * 1024 * 1024
        sz = path.stat().st_size
        if sz <= max_bytes:
            return
        # crude truncation strategy: load objs, sort by ts desc, keep until byte budget
        lines = path.read_text(encoding='utf-8').splitlines()
        objs = []
        for ln in lines:
            try:
                o = json.loads(ln)
                objs.append(o)
            except Exception:
                continue
        objs.sort(key=lambda o: o.get('ts', 0), reverse=True)
        new_lines = []
        total = 0
        for o in objs:
            js = json.dumps(o, ensure_ascii=False)
            bs = len(js.encode('utf-8')) + 1
            if total + bs > max_bytes:
                break
            new_lines.append(js)
            total += bs
        path.write_text('\n'.join(new_lines) + ('\n' if new_lines else ''), encoding='utf-8')
    except Exception:
        pass

def purge_old(max_entries: int | None = None):
    path = _skills_cache_path()
    if not path.exists():
        return
    try:
        if max_entries is None:
            env_limit = os.getenv('SCRAPER_SKILL_CACHE_MAX_ENTRIES')
            if env_limit and env_limit.isdigit():
                try:
                    max_entries = int(env_limit)
                except ValueError:
                    max_entries = SETTINGS.skill_cache_max_entries
            else:
                max_entries = SETTINGS.skill_cache_max_entries
        lines = path.read_text(encoding='utf-8').splitlines()
        if len(lines) <= max_entries:
            _enforce_disk_size(path)
            return
        # keep newest by ts
        objs = []
        for ln in lines:
            try:
                o = json.loads(ln)
                objs.append(o)
            except Exception:
                continue
        objs.sort(key=lambda o: o.get('ts', 0), reverse=True)
        keep = objs[:max_entries]
        with path.open('w', encoding='utf-8') as f:
            for o in keep:
                f.write(json.dumps(o, ensure_ascii=False) + '\n')
        _enforce_disk_size(path)
    except Exception:
        pass

def clear_skills_cache():
    path = _skills_cache_path()
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass

def should_clear_env_flag() -> bool:
    return os.environ.get('SCRAPER_CLEAR_SKILL_CACHE') == '1'
