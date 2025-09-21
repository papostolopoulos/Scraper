from __future__ import annotations
from pathlib import Path
import yaml
from typing import Dict, List, Set

_CACHE: Dict[str, Dict[str, List[str]]] = {}

_DEF_PATH = Path('scraper/config/skill_dependencies.yml')

def load_dependencies(refresh: bool = False) -> Dict[str, List[str]]:
    global _CACHE
    if not refresh and 'deps' in _CACHE:
        return _CACHE['deps']
    deps: Dict[str, List[str]] = {}
    if _DEF_PATH.exists():
        try:
            with open(_DEF_PATH, 'r', encoding='utf-8') as f:
                raw = yaml.safe_load(f) or {}
            if isinstance(raw, dict):
                for k,v in raw.items():
                    if isinstance(v, list):
                        deps[str(k).lower()] = [str(x).lower() for x in v if x]
        except Exception:
            pass
    _CACHE['deps'] = deps
    return deps

def unresolved_prereqs(skill: str, achieved: Set[str]) -> List[str]:
    deps = load_dependencies()
    skill_l = skill.lower()
    reqs = deps.get(skill_l, [])
    return [r for r in reqs if r not in achieved]

def topological_sort(skills: List[str]) -> List[str]:
    # Basic stable ordering based on dependency presence (skills with fewer unmet deps earlier)
    deps = load_dependencies()
    def score(s: str) -> int:
        return len(deps.get(s.lower(), []))
    return sorted(skills, key=score)
