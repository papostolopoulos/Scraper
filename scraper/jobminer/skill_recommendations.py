from __future__ import annotations
from pathlib import Path
import yaml
from typing import Dict, Any, List

_CACHE: Dict[str, Dict[str, Any]] = {}

def _config_root() -> Path:
    # Assuming this file sits under scraper/jobminer
    return Path('scraper/config')

def load_recommendations(refresh: bool = False) -> Dict[str, Dict[str, Any]]:
    global _CACHE
    key = 'recs'
    if not refresh and key in _CACHE:
        return _CACHE[key]
    path = _config_root() / 'skill_recommendations.yml'
    recs: Dict[str, Dict[str, Any]] = {}
    if path.exists():
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw = yaml.safe_load(f) or {}
            if isinstance(raw, dict):
                for k,v in raw.items():
                    if not isinstance(v, dict):
                        continue
                    recs[str(k).lower()] = {
                        'suggested_action': v.get('suggested_action'),
                        'resource_url': v.get('resource_url'),
                        'resume_phrase': v.get('resume_phrase'),
                    }
        except Exception:
            pass
    _CACHE[key] = recs
    return recs

def enrich_gap_skills(gaps: List[Dict[str, Any]], max_items: int = 10) -> List[Dict[str, Any]]:
    recs = load_recommendations()
    enriched = []
    for g in gaps[:max_items]:
        skill_key = g.get('skill','').lower()
        rec = recs.get(skill_key, {})
        item = dict(g)
        if rec:
            item['suggested_action'] = rec.get('suggested_action')
            item['resource_url'] = rec.get('resource_url')
            item['resume_phrase'] = rec.get('resume_phrase')
        enriched.append(item)
    return enriched
