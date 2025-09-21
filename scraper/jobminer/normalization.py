"""Deterministic fuzzy normalization helpers for duplicate signature generation.

These helpers apply conservative, rule-based normalization (no ML / heavy fuzzy)
to reduce superficial variance across sources. They are only used when the
`JOBMINER_FUZZY_NORMALIZATION` toggle is enabled (see settings.fuzzy_normalization).
"""
from __future__ import annotations
import re

_COMPANY_SUFFIX_RE = re.compile(r"\b(inc|inc\.|corp|corp\.|ltd|ltd\.|llc|gmbh|sa|bv|ag)\b", re.IGNORECASE)
_PUNCT_RE = re.compile(r"[^a-z0-9]+")
_MULTISPACE_RE = re.compile(r"\s+")

_TITLE_ABBR = {
    'sr': 'senior',
    'jr': 'junior',
    'dev': 'developer',
    'eng': 'engineer'
}

_STATE_ABBR = {
    'ca': 'california','ny': 'new york','wa':'washington','tx':'texas','fl':'florida','il':'illinois','ma':'massachusetts','pa':'pennsylvania'
}

def _canonical_space(s: str) -> str:
    return _MULTISPACE_RE.sub(' ', s).strip()

def normalize_company(name: str | None) -> str:
    if not name:
        return ''
    s = name.lower()
    # remove leading 'the '
    if s.startswith('the '):
        s = s[4:]
    # remove punctuation early for consistent token boundaries
    s = _PUNCT_RE.sub(' ', s)
    # strip corporate suffix tokens as standalone tokens
    s = _COMPANY_SUFFIX_RE.sub(' ', s)
    # remove stray 1-char or non-alphanumeric tokens
    tokens = [t for t in s.split() if any(c.isalnum() for c in t) and len(t) > 1]
    s = ' '.join(tokens)
    return _canonical_space(s)

def normalize_title(title: str | None) -> str:
    if not title:
        return ''
    s = _PUNCT_RE.sub(' ', title.lower())
    tokens = []
    for t in s.split():
        repl = _TITLE_ABBR.get(t, t)
        tokens.append(repl)
    return _canonical_space(' '.join(tokens))

def normalize_location(loc: str | None) -> str:
    if not loc:
        return ''
    s = loc.lower()
    # unify saint/st variants
    s = s.replace('saint ', 'st ').replace('st. ', 'st ')
    # punctuation to spaces
    s = _PUNCT_RE.sub(' ', s)
    tokens = []
    for t in s.split():
        tokens.append(_STATE_ABBR.get(t, t))
    # limit depth (city state country) -> first 3 tokens
    s2 = ' '.join(tokens[:3])
    return _canonical_space(s2)

__all__ = [
    'normalize_company','normalize_title','normalize_location'
]
