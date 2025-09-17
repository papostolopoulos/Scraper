"""Lightweight semantic enrichment refinement.

Goal: Provide deterministic, dependency-light expansion of matched skills:
 - Converts job description and seed skills into TF-IDF vectors using a simple
   corpus built from: job description, resume skills phrases, and optional extra
   vocabulary (future extension).
 - Computes cosine similarity between each seed skill phrase and full text; if
   above threshold and not already extracted by heuristic pipeline, add as
   "semantic" skill.
 - For multi-word phrases partially matched heuristically, may boost score.

Determinism: no randomness; ordering rule:
   1. Existing extracted (heuristic) skills keep their order.
   2. New semantic additions appended sorted by descending similarity then
      original seed order as tiebreaker.

No external heavy ML dependencies; implements a minimal TF-IDF + cosine.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Iterable, Tuple, Optional
import math
import re
import os
from pathlib import Path
import yaml

TOKEN_RE = re.compile(r"[a-zA-Z0-9+.#-]+")

def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]

def _ngram_tokens(tokens: List[str], n: int) -> Iterable[str]:
    for i in range(len(tokens)):
        yield tokens[i]
        if n >= 2 and i + 1 < len(tokens):
            yield tokens[i] + "_" + tokens[i + 1]

def _tf(tokens: List[str]) -> dict:
    d: dict[str, int] = {}
    for t in tokens:
        d[t] = d.get(t, 0) + 1
    return d

def _idf(doc_freq: dict[str, int], total_docs: int) -> dict[str, float]:
    return {t: math.log((1 + total_docs) / (1 + df)) + 1 for t, df in doc_freq.items()}

def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    num = 0.0
    for k, va in a.items():
        vb = b.get(k)
        if vb is not None:
            num += va * vb
    if not num:
        return 0.0
    na = math.sqrt(sum(v*v for v in a.values()))
    nb = math.sqrt(sum(v*v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return num / (na * nb)

def _tfidf_vector(tokens: List[str], idf: dict[str, float]) -> dict[str, float]:
    tf = _tf(tokens)
    return {t: freq * idf.get(t, 0.0) for t, freq in tf.items()}

@dataclass
class SemanticResult:
    skill: str
    similarity: float

class SemanticEnricher:
    def __init__(self, similarity_threshold: Optional[float] = None, enable_bigrams: Optional[bool] = None, max_new: Optional[int] = None, config_root: Optional[Path] = None):
        # Load config from file with env var overrides; allow direct parameters to override all
        cfg = self._load_config(config_root)
        thr = similarity_threshold if similarity_threshold is not None else cfg.get('similarity_threshold', 0.32)
        big = enable_bigrams if enable_bigrams is not None else bool(cfg.get('enable_bigrams', True))
        cap = max_new if max_new is not None else int(cfg.get('max_new', 15))
        self.similarity_threshold = float(os.getenv('SCRAPER_SEMANTIC_THRESHOLD', thr))
        env_big = os.getenv('SCRAPER_SEMANTIC_ENABLE_BIGRAMS')
        self.enable_bigrams = (env_big.lower() in ('1','true','yes','on')) if env_big is not None else bool(big)
        self.max_new = int(os.getenv('SCRAPER_SEMANTIC_MAX_NEW', cap))

    def _load_config(self, config_root: Optional[Path]) -> dict:
        try:
            root = Path(config_root) if config_root else Path(__file__).resolve().parents[2]
            cfg_path = root / 'config' / 'semantic.yml'
            if cfg_path.exists():
                return yaml.safe_load(cfg_path.read_text(encoding='utf-8')) or {}
        except Exception:
            return {}
        return {}

    def _seed_tokens_cached(self, seed_skills: List[str]) -> List[List[str]]:
        # Simple memoization keyed by (enable_bigrams, tuple(seed_skills))
        key = (self.enable_bigrams, tuple(seed_skills))
        cache = getattr(self, '_seed_cache', None)
        if cache is None:
            cache = {}
            self._seed_cache = cache
        if key in cache:
            return cache[key]
        token_lists = [list(_ngram_tokens(_tokenize(s), 2 if self.enable_bigrams else 1)) for s in seed_skills]
        cache[key] = token_lists
        return token_lists

    def enrich(self, description: str, heuristic_skills: List[str], seed_skills: List[str]) -> List[str]:
        if not description or not seed_skills:
            return heuristic_skills
        # Build corpus docs: description + each seed phrase
        desc_tokens = list(_ngram_tokens(_tokenize(description), 2 if self.enable_bigrams else 1))
        seed_token_lists = self._seed_tokens_cached(seed_skills)
        docs = [desc_tokens] + seed_token_lists
        # document frequency
        doc_freq: dict[str, int] = {}
        for dtoks in docs:
            for t in set(dtoks):
                doc_freq[t] = doc_freq.get(t, 0) + 1
        idf = _idf(doc_freq, len(docs))
        vectors = [_tfidf_vector(dt, idf) for dt in docs]
        desc_vec = vectors[0]
        existing_lower = {s.lower() for s in heuristic_skills}
        results: List[SemanticResult] = []
        for seed, vec in zip(seed_skills, vectors[1:]):
            if seed.lower() in existing_lower:
                continue
            sim = _cosine(vec, desc_vec)
            if sim >= self.similarity_threshold:
                results.append(SemanticResult(skill=seed, similarity=sim))
        # order: descending similarity then original seed order
        seed_index = {s: i for i, s in enumerate(seed_skills)}
        results.sort(key=lambda r: (-r.similarity, seed_index[r.skill]))
        if self.max_new is not None and self.max_new >= 0:
            results = results[: self.max_new]
        return heuristic_skills + [r.skill for r in results]

__all__ = ["SemanticEnricher"]