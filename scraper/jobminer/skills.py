from __future__ import annotations
from pathlib import Path
from typing import List, Tuple
import re

# rapidfuzz is heavy; defer import until needed
def _fuzz_partial_ratio(a: str, b: str) -> int:
    from rapidfuzz import fuzz  # type: ignore
    return fuzz.partial_ratio(a, b)

def load_seed_skills(path: Path) -> List[str]:
    if not path.exists():
        return []
    return [l.strip() for l in path.read_text(encoding='utf-8').splitlines() if l.strip()]


def _stem(token: str) -> str:
    for suf in ('ing', 'ers', 'er', 'ies', 's'):
        if token.endswith(suf) and len(token) - len(suf) >= 3:
            return token[:-len(suf)]
    return token

def extract_resume_overlap_skills(description: str, resume_skills: List[str], coverage_threshold: float = 0.6) -> List[str]:
    """Return subset of resume skills that appear (loosely) in description.
    Matching rules:
      - Tokenize & stem both sides.
      - A multi-word resume skill matches if >= coverage_threshold of its stem tokens appear in description stems.
      - Single-word skill matches if stem appears.
      - Fuzzy fallback: phrase partial_ratio >= 82.
    Preserves original resume skill order.
    """
    if not description or not resume_skills:
        return []
    desc_tokens = [_stem(t) for t in re.findall(r"[a-zA-Z0-9+.#-]+", description.lower())]
    desc_set = set(desc_tokens)
    out = []
    for skill in resume_skills:
        raw = skill.strip()
        if not raw:
            continue
        parts = re.findall(r"[a-zA-Z0-9+.#-]+", raw.lower())
        stems = [_stem(p) for p in parts]
        if not stems:
            continue
        if len(stems) == 1:
            if stems[0] in desc_set:
                out.append(raw)
            elif _fuzz_partial_ratio(raw.lower(), ' '.join(desc_tokens)) >= 90:
                out.append(raw)
            continue
        present = sum(1 for s in stems if s in desc_set)
        coverage = present / len(stems)
        if coverage >= coverage_threshold or _fuzz_partial_ratio(raw.lower(), description.lower()) >= 82:
            out.append(raw)
    return out

def extract_skills(description: str, seed_skills: List[str], window: int = 8) -> List[str]:
    """Improved heuristic skill extraction.
    Changes vs previous:
      - Accept 70% token coverage (anywhere) for multi-word skill.
      - Lower fuzzy threshold to 80.
      - Keep proximity boost if tokens occur within window span.
      - Synonym normalization (programme->program, e-mail->email, infra->infrastructure, k8s->kubernetes).
      - Light stemming + plural/verb form stripping.
      - Score = coverage + proximity_bonus + frequency*0.05.
    Returns up to 40 skills ordered by score then original order.
    """
    if not description or not seed_skills:
        return []
    norm_map = {
        'programme': 'program', 'e-mail': 'email', 'infra': 'infrastructure', 'k8s': 'kubernetes'
    }
    text = description.lower()
    for k, v in norm_map.items():
        text = text.replace(k, v)
    raw_tokens = re.findall(r"[a-zA-Z0-9+.#-]+", text)
    raw_tokens = [norm_map.get(t, t) for t in raw_tokens]
    stem_tokens = [_stem(t) for t in raw_tokens]
    stem_set = set(stem_tokens)
    positions = {}
    for idx, tok in enumerate(stem_tokens):
        positions.setdefault(tok, []).append(idx)

    MIN_COVERAGE_RATIO = 0.7
    FUZZ_THRESHOLD = 80
    results: List[Tuple[str, float]] = []
    seen = set()
    for raw_skill in seed_skills:
        skill = raw_skill.strip()
        if not skill:
            continue
        key = skill.lower()
        if key in seen:
            continue
        norm_key = key
        for k, v in norm_map.items():
            norm_key = norm_key.replace(k, v)
        parts = re.findall(r"[a-zA-Z0-9+.#-]+", norm_key)
        parts_stem = [_stem(p) for p in parts]
        n_parts = len(parts_stem)
        matched = False
        coverage = 0
        proximity_bonus = 0.0
        if n_parts > 1:
            present = [p for p in parts_stem if p in stem_set]
            coverage = len(present)
            if coverage / n_parts >= MIN_COVERAGE_RATIO and coverage > 0:
                matched = True
                # proximity evaluation using first occurrence of each present token
                present_positions = [positions[p][0] for p in present if positions.get(p)]
                if present_positions:
                    span = max(present_positions) - min(present_positions)
                    if span <= window:
                        proximity_bonus = 0.5
            if not matched and _fuzz_partial_ratio(norm_key, text) >= FUZZ_THRESHOLD:
                matched = True
                coverage = n_parts
        else:
            token = parts_stem[0]
            if token in stem_set or re.search(rf"\b{re.escape(parts[0])}\b", text):
                matched = True
                coverage = 1
        if matched:
            freq = sum(len(positions.get(p, [])) for p in parts_stem)
            score = coverage + proximity_bonus + freq * 0.05
            results.append((raw_skill, score))
            seen.add(key)
    results.sort(key=lambda x: (-x[1], seed_skills.index(x[0])))
    return [s for s, _ in results[:40]]
