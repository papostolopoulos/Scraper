from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List, Optional
import json, time, threading

_PROGRESS_FILE = Path('scraper/data/skill_progress.json')
_LOCK = threading.Lock()
_VALID_STATUSES = {'planned','in_progress','achieved','archived'}

def _ensure_dir():
    _PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)

def load_progress() -> Dict[str, Dict[str, Any]]:
    _ensure_dir()
    if not _PROGRESS_FILE.exists():
        return {}
    try:
        with open(_PROGRESS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f) or {}
            # Normalize keys
            fixed = {}
            for k,v in data.items():
                if isinstance(v, dict):
                    fixed[k.lower()] = v
            return fixed
    except Exception:
        return {}

def save_progress(progress: Dict[str, Dict[str, Any]]):
    _ensure_dir()
    tmp = _PROGRESS_FILE.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)
    tmp.replace(_PROGRESS_FILE)


def upsert_progress(skill: str, status: str, note: Optional[str] = None) -> Dict[str, Any]:
    skill_key = skill.lower().strip()
    if not skill_key:
        raise ValueError('skill required')
    if status not in _VALID_STATUSES:
        raise ValueError(f'status must be one of {_VALID_STATUSES}')
    now = int(time.time())
    with _LOCK:
        data = load_progress()
        existing = data.get(skill_key)
        if existing:
            existing['status'] = status
            existing['updated_at'] = now
            if note is not None:
                existing['note'] = note
        else:
            data[skill_key] = {
                'skill': skill_key,
                'status': status,
                'first_seen': now,
                'updated_at': now,
            }
            if note:
                data[skill_key]['note'] = note
        save_progress(data)
        return data[skill_key]


def list_progress(filter_status: Optional[str] = None) -> List[Dict[str, Any]]:
    data = load_progress()
    rows = list(data.values())
    if filter_status:
        rows = [r for r in rows if r.get('status') == filter_status]
    # Sort by status then updated_at desc
    rows.sort(key=lambda r: (r.get('status'), -r.get('updated_at', 0)))
    return rows


def get_progress_for(skills: List[str]) -> Dict[str, Dict[str, Any]]:
    data = load_progress()
    out = {}
    for s in skills:
        k = s.lower()
        if k in data:
            out[k] = data[k]
    return out
