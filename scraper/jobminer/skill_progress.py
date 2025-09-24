from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List, Optional
import json, time, threading, os, tempfile

_PROGRESS_FILE = Path('scraper/data/skill_progress.json')
_LOCK = threading.Lock()
_VALID_STATUSES = {'planned','in_progress','achieved','archived'}
_SECONDS_PER_WEEK = 7 * 24 * 3600

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
    # Write to a uniquely named temp file in the same directory to avoid Windows file contention
    dirpath = _PROGRESS_FILE.parent
    tmp_fd, tmp_path = tempfile.mkstemp(prefix='skill_progress_', suffix='.tmp', dir=dirpath)
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
        # Try atomic replace with a short retry loop for Windows
        for _ in range(3):
            try:
                os.replace(tmp_path, _PROGRESS_FILE)
                break
            except PermissionError:
                time.sleep(0.05)
        else:
            # Final attempt, may raise
            os.replace(tmp_path, _PROGRESS_FILE)
    finally:
        # Ensure temp file is removed if replace failed earlier
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


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
            prev_status = existing.get('status')
            if prev_status != status:
                # Append to history
                hist = existing.setdefault('history', [])
                hist.append({'status': status, 'ts': now})
            existing['status'] = status
            existing['updated_at'] = now
            if note is not None:
                existing['note'] = note
        else:
            record = {
                'skill': skill_key,
                'status': status,
                'first_seen': now,
                'updated_at': now,
                'history': [{'status': status, 'ts': now}],
            }
            if note:
                record['note'] = note
            data[skill_key] = record
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


def compute_velocity_metrics(weeks: int = 8) -> Dict[str, Any]:
    """Compute weekly cumulative counts and achieved deltas for the last N weeks.
    Returns structure:
    {
      'weeks': [ { 'week_start': iso_date, 'planned': int, 'in_progress': int, 'achieved': int, 'archived': int, 'achieved_delta': int } ... ],
      'current': { 'planned': int, 'in_progress': int, 'achieved': int, 'archived': int },
      'velocity_avg_4w': float  # average achieved_delta over last 4 full weeks (if available)
    }
    Week boundaries use Monday 00:00 UTC as anchor for consistency.
    """
    data = load_progress()
    if weeks < 1:
        weeks = 1
    now = int(time.time())
    # Determine start of current week (Monday 00:00 UTC)
    import datetime as _dt
    utc_now = _dt.datetime.utcfromtimestamp(now)
    weekday = utc_now.weekday()  # Monday=0
    start_of_week = utc_now - _dt.timedelta(days=weekday, hours=utc_now.hour, minutes=utc_now.minute, seconds=utc_now.second, microseconds=utc_now.microsecond)
    start_ts = int(start_of_week.timestamp())
    week_boundaries = [start_ts - i * _SECONDS_PER_WEEK for i in range(weeks)][::-1]
    # Prepare buckets
    buckets = []
    # We'll compute status at each week boundary by replaying histories.
    # Build events list: (ts, skill, status)
    events = []
    for rec in data.values():
        hist = rec.get('history') or []
        for h in hist:
            ts = int(h.get('ts', rec.get('first_seen', 0)))
            st = h.get('status') or rec.get('status')
            events.append((ts, rec.get('skill'), st))
    # Sort events chronologically
    events.sort(key=lambda x: x[0])
    # Replay to get status at each boundary
    status_by_skill: Dict[str,str] = {}
    idx = 0
    n_events = len(events)
    for i, boundary in enumerate(week_boundaries):
        # apply events up to this boundary (exclusive next boundary, inclusive current)
        while idx < n_events and events[idx][0] < boundary + _SECONDS_PER_WEEK:
            ts, sk, st = events[idx]
            if ts <= boundary + _SECONDS_PER_WEEK - 1:
                if st in _VALID_STATUSES:
                    status_by_skill[sk] = st
            idx += 1
        # Count statuses for all skills current known up to boundary
        counts = {s: 0 for s in _VALID_STATUSES}
        for st in status_by_skill.values():
            counts[st] = counts.get(st, 0) + 1
        buckets.append({
            'week_start': _dt.datetime.utcfromtimestamp(boundary).date().isoformat(),
            'planned': counts.get('planned', 0),
            'in_progress': counts.get('in_progress', 0),
            'achieved': counts.get('achieved', 0),
            'archived': counts.get('archived', 0),
        })
    # Compute achieved_delta vs prior week
    prev = None
    for b in buckets:
        if prev is None:
            b['achieved_delta'] = b['achieved']
        else:
            b['achieved_delta'] = b['achieved'] - prev['achieved']
        prev = b
    # Average last up-to 4 full week deltas (excluding current partial week -> last entry is current week)
    last_full = buckets[:-1]
    recent = last_full[-4:] if len(last_full) >= 4 else last_full
    velocity_avg_4w = sum(b['achieved_delta'] for b in recent) / len(recent) if recent else 0.0
    current_counts = buckets[-1] if buckets else {'planned':0,'in_progress':0,'achieved':0,'archived':0}
    return {
        'weeks': buckets,
        'current': {k: current_counts[k] for k in ['planned','in_progress','achieved','archived'] if k in current_counts},
        'velocity_avg_4w': round(velocity_avg_4w, 2),
    }
