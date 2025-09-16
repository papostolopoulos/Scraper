from __future__ import annotations
"""Compensation & benefit normalization utilities.

Goals:
 - Currency conversion to a canonical currency (USD) using config-specified rates.
 - Annualization of salaries if provided in monthly / hourly units (simple heuristic multipliers).
 - Benefit keyword mapping to a canonical set (case-insensitive containment or exact match).

Config Files (YAML):
 - config/compensation.yml
     base_currency: USD
     currency_rates: { EUR: 1.08, GBP: 1.27, CAD: 0.74 }
     unit_multipliers: { yearly: 1, annual: 1, monthly: 12, hour: 2080 }
 - config/benefits.yml
     mappings:
       health: ["health insurance","medical","medical insurance","medical plan"]
       401k: ["401k","401(k)"]
       remote: ["remote work","work from home","wfh"]

The loader is resilient: missing files => defaults. Unknown currency returns None conversion.
"""
from pathlib import Path
import yaml
from typing import Dict, List, Optional, Tuple

DEFAULT_COMP_CONFIG = {
    'base_currency': 'USD',
    'currency_rates': {},
    'unit_multipliers': {'yearly': 1, 'annual': 1, 'monthly': 12, 'hour': 2080}
}

def _load_yaml(path: Path) -> Dict:
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
            return data
    except Exception:
        return {}

def load_comp_config(root: Path) -> Dict:
    cfg = DEFAULT_COMP_CONFIG.copy()
    user_cfg = _load_yaml(root / 'config' / 'compensation.yml')
    if 'base_currency' in user_cfg:
        cfg['base_currency'] = user_cfg['base_currency']
    if 'currency_rates' in user_cfg:
        cfg['currency_rates'].update(user_cfg['currency_rates'] or {})
    if 'unit_multipliers' in user_cfg:
        cfg['unit_multipliers'].update(user_cfg['unit_multipliers'] or {})
    return cfg

def load_benefit_mappings(root: Path) -> Dict[str, List[str]]:
    data = _load_yaml(root / 'config' / 'benefits.yml')
    mappings = data.get('mappings', {}) if isinstance(data, dict) else {}
    norm_map = {}
    for canon, variants in mappings.items():
        if not isinstance(variants, list):
            continue
        norm_map[canon.lower()] = [v.lower() for v in variants]
    return norm_map

def convert_salary(min_v: Optional[float], max_v: Optional[float], currency: Optional[str], unit: Optional[str], comp_cfg: Dict) -> Tuple[Optional[float], Optional[float]]:
    if min_v is None and max_v is None:
        return None, None
    base = comp_cfg['base_currency']
    rates = comp_cfg['currency_rates']
    mults = comp_cfg['unit_multipliers']
    cur = (currency or base or '').upper()
    unit_key = (unit or 'yearly').lower()
    rate = 1.0
    if cur != base:
        rate = rates.get(cur, None)
        if rate is None:
            return None, None
    annual_mult = mults.get(unit_key, 1)
    def _c(v):
        if v is None:
            return None
        try:
            return round(float(v) * rate * annual_mult, 2)
        except Exception:
            return None
    return _c(min_v), _c(max_v)

def map_benefits(raw_benefits: List[str], mapping: Dict[str, List[str]]) -> List[str]:
    if not raw_benefits:
        return []
    canon_hits = set()
    for raw in raw_benefits:
        low = raw.lower().strip()
        for canon, variants in mapping.items():
            if low == canon or low in variants:
                canon_hits.add(canon)
            else:
                # containment heuristic (avoid overmatching very short tokens)
                if len(low) > 5:
                    for v in variants:
                        if len(v) > 5 and v in low:
                            canon_hits.add(canon)
                            break
    return sorted(canon_hits)

__all__ = [
    'load_comp_config','load_benefit_mappings','convert_salary','map_benefits'
]