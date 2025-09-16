"""Unified semantic enrichment toggle resolution.

Precedence (highest wins):
 1. Explicit function argument (if provided by caller)
 2. CLI flag / runtime override via env vars:
       SCRAPER_NO_SEMANTIC=1  -> force disable
       SCRAPER_SEMANTIC_ENABLE=0/1 -> explicit enable/disable
 3. matching.yml semantic.enable (default True if absent)

Expose helper `semantic_enabled(matching_cfg: dict, override: bool | None = None) -> bool`.
"""
from __future__ import annotations
import os

def semantic_enabled(matching_cfg: dict | None, override: bool | None = None) -> bool:
    if override is not None:
        return bool(override)
    # Env explicit off wins
    if os.getenv('SCRAPER_NO_SEMANTIC') == '1':
        return False
    env_toggle = os.getenv('SCRAPER_SEMANTIC_ENABLE')
    if env_toggle is not None:
        if env_toggle.strip() in ('0','false','False'):
            return False
        if env_toggle.strip() in ('1','true','True'):
            return True
    if matching_cfg is None:
        return True
    return bool(matching_cfg.get('semantic', {}).get('enable', True))

__all__ = ['semantic_enabled']