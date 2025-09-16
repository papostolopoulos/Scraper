"""Weights configuration loader and validator.

Supports environment override via SCRAPER_WEIGHTS_FILE.
Validation rules:
  - Required weight keys: skill, semantic, recency, seniority, company
  - Each weight >0 and <=1.5
  - Sum of weights between 0.8 and 1.5 (inclusive) (guard extreme scaling)
  - Thresholds require: shortlist, review with 0<=review<shortlist<=1
Errors raise ValueError with a concise message listing problems.
"""
from __future__ import annotations
from pathlib import Path
import os, yaml
from typing import Tuple, Dict

WEIGHT_KEYS = ["skill","semantic","recency","seniority","company"]
THRESHOLD_KEYS = ["shortlist","review"]

_CACHE: Tuple[Dict[str,float], Dict[str,float]] | None = None

CONFIG_DIR = Path(__file__).resolve().parent.parent / 'config'

def _resolve_file() -> Path:
    override = os.getenv('SCRAPER_WEIGHTS_FILE')
    if override:
        p = Path(override)
        if not p.exists():
            raise ValueError(f"Weights file override not found: {p}")
        return p
    return CONFIG_DIR / 'weights.yml'

def _validate(weights: Dict[str, float], thresholds: Dict[str, float]):
    errors = []
    missing = [k for k in WEIGHT_KEYS if k not in weights]
    if missing:
        errors.append(f"missing weight keys: {', '.join(missing)}")
    for k,v in weights.items():
        try:
            fv = float(v)
        except Exception:  # type: ignore
            errors.append(f"weight '{k}' not numeric")
            continue
        if fv <= 0:
            errors.append(f"weight '{k}' must be > 0")
        if fv > 1.5:
            errors.append(f"weight '{k}' too large (>1.5)")
    total = sum(float(weights.get(k,0)) for k in WEIGHT_KEYS)
    if total and not (0.8 <= total <= 1.5):
        errors.append(f"total weights sum {total:.3f} outside [0.8,1.5]")
    # thresholds
    th_missing = [k for k in THRESHOLD_KEYS if k not in thresholds]
    if th_missing:
        errors.append(f"missing thresholds: {', '.join(th_missing)}")
    else:
        try:
            shortlist = float(thresholds['shortlist'])
            review = float(thresholds['review'])
            if not (0 <= review < shortlist <= 1):
                errors.append("threshold relation must satisfy 0 <= review < shortlist <= 1")
        except Exception:
            errors.append("threshold values must be numeric")
    if errors:
        raise ValueError("Invalid weights config: " + "; ".join(errors))

def load_weights(force_reload: bool = False):
    """Return (weights, thresholds) dicts with validation and caching."""
    global _CACHE
    if _CACHE is not None and not force_reload:
        return _CACHE
    file_path = _resolve_file()
    raw = yaml.safe_load(file_path.read_text(encoding='utf-8')) or {}
    weights = raw.get('weights') or {}
    thresholds = raw.get('thresholds') or {}
    _validate(weights, thresholds)
    # ensure floats
    weights = {k: float(weights[k]) for k in WEIGHT_KEYS}
    thresholds = {k: float(thresholds[k]) for k in THRESHOLD_KEYS}
    _CACHE = (weights, thresholds)
    return _CACHE

__all__ = ["load_weights","WEIGHT_KEYS"]
