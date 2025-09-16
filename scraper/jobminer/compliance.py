from __future__ import annotations
"""Compliance / Terms-of-Service gating utilities.

The project intentionally requires an explicit opt-in before running automated
collection against external sites to encourage mindful, low-volume usage
consistent with site policies.

Opt-in mechanisms (highest precedence first):
 1. CLI flag: --allow-automation
 2. Environment: SCRAPER_ALLOW_AUTOMATION=1
 3. Config file: config/compliance.yml with allow_automation: true

If none are present/true, automation_allowed() returns False and the caller
should refuse to perform collection.
"""
from pathlib import Path
import os, yaml
from typing import Optional

def _load_config(base: Path) -> dict:
    path = base / 'config' / 'compliance.yml'
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    except Exception:
        return {}

def automation_allowed(base: Path, cli_flag: Optional[bool] = None) -> bool:
    if cli_flag is True:
        return True
    if cli_flag is False:  # explicit deny (not strictly needed but symmetric)
        return False
    env_v = os.getenv('SCRAPER_ALLOW_AUTOMATION')
    if env_v is not None:
        return env_v.lower() in ('1','true','yes','on')
    cfg = _load_config(base)
    return bool(cfg.get('allow_automation', False))

__all__ = ['automation_allowed']