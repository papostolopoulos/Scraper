from __future__ import annotations
"""Redaction utilities for exports.

Allows masking of potential PII or sensitive tokens (emails, phone numbers, URLs) in export fields.
Patterns configurable via YAML at config/redaction.yml

Example config:

enabled: true
rules:
  email: '\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b'
  phone: '(?:\+?\d[\d\s().-]{6,}\d)'
  url: 'https?://[^\s]+'
replacement: '[REDACTED]'

If file missing: defaults applied. Users can disable via enabled: false or env SCRAPER_REDACT_EXPORT=0.
"""
from pathlib import Path
import os, re, yaml
from typing import Dict, Iterable

DEFAULT_RULES = {
    'email': r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b',
    'phone': r'(?:\+?\d[\d\s().-]{6,}\d)',  # loose pattern for international
    'url': r'https?://[^\s]+' ,
}

def load_redaction_config(root: Path) -> Dict:
    path = root / 'config' / 'redaction.yml'
    data = {}
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        except Exception:
            data = {}
    cfg = {
        'enabled': data.get('enabled', True),
        'rules': {**DEFAULT_RULES, **(data.get('rules') or {})},
        'replacement': data.get('replacement', '[REDACTED]')
    }
    # Env override to force on/off
    env_v = os.getenv('SCRAPER_REDACT_EXPORT')
    if env_v is not None:
        cfg['enabled'] = env_v.lower() in ('1','true','yes','on')
    # Precompile
    compiled = {}
    for name, patt in cfg['rules'].items():
        try:
            compiled[name] = re.compile(patt, re.IGNORECASE)
        except re.error:
            continue
    cfg['compiled'] = compiled
    return cfg

def redact_text(text: str, cfg: Dict) -> str:
    if not text or not cfg.get('enabled'):
        return text
    rep = cfg.get('replacement', '[REDACTED]')
    for patt in cfg.get('compiled', {}).values():
        text = patt.sub(rep, text)
    return text

def redact_fields(record: Dict, field_names: Iterable[str], cfg: Dict) -> Dict:
    if not cfg.get('enabled'):
        return record
    for f in field_names:
        if f in record and isinstance(record[f], str):
            record[f] = redact_text(record[f], cfg)
    return record

__all__ = ['load_redaction_config','redact_text','redact_fields']