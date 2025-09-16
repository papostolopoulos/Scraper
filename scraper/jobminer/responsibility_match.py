from __future__ import annotations
from typing import List, Dict, Tuple
import re
from dataclasses import dataclass
from rapidfuzz import fuzz

try:
    from sentence_transformers import SentenceTransformer, util
except ImportError:  # graceful fallback
    SentenceTransformer = None
    util = None

EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
_sent_model = None


def get_sentence_model():
    global _sent_model
    if _sent_model is None and SentenceTransformer:
        _sent_model = SentenceTransformer(EMBED_MODEL_NAME)
    return _sent_model


STOP = set("the a an of and or to for with on in by at from through across into using via as is are were was be being been that this those these it its their our your your".split())


def _norm_tokens(text: str) -> List[str]:
    toks = re.findall(r"[a-zA-Z0-9+.#-]+", text.lower())
    out = []
    for t in toks:
        if t in STOP:
            continue
        if len(t) <= 2 and not t.isupper():  # keep short ALLCAPS like QA, ML
            continue
        out.append(t)
    return out


def sentence_split(text: str) -> List[str]:
    if not text:
        return []
    # rudimentary split safe for job descriptions
    pieces = re.split(r"(?<=[.!?])\s+", text.strip())
    # further split overly long pieces
    out = []
    for p in pieces:
        if len(p) > 400:
            # chunk by semicolon or commas
            sub = re.split(r"[;]\s+", p)
            out.extend([s.strip() for s in sub if s.strip()])
        else:
            out.append(p.strip())
    return [s for s in out if len(s.split()) >= 3]


@dataclass
class ResponsibilityOverlap:
    responsibility: str
    best_sentence: str | None
    coverage: float
    overlap_tokens: List[str]
    fuzzy: int


def compute_overlap(responsibilities: List[str], job_text: str, min_coverage: float = 0.4, min_fuzzy: int = 82) -> List[ResponsibilityOverlap]:
    job_tokens = _norm_tokens(job_text)
    job_token_set = set(job_tokens)
    sentences = sentence_split(job_text)[:120]
    results: List[ResponsibilityOverlap] = []
    for resp in responsibilities:
        rtoks = _norm_tokens(resp)
        if not rtoks:
            continue
        overlap = [t for t in rtoks if t in job_token_set]
        coverage = len(overlap) / len(rtoks)
        best_sentence = None
        fuzzy_score = fuzz.partial_ratio(resp.lower(), job_text.lower())
        if sentences:
            # choose sentence with max token overlap count
            best_sentence = max(sentences, key=lambda s: sum(1 for t in rtoks if t in _norm_tokens(s)))
        if coverage >= min_coverage or fuzzy_score >= min_fuzzy:
            results.append(ResponsibilityOverlap(resp, best_sentence, round(coverage,3), overlap, fuzzy_score))
    return results


@dataclass
class SemanticMatch:
    responsibility: str
    job_sentence: str
    similarity: float


def compute_semantic_matches(responsibilities: List[str], job_text: str, min_similarity: float = 0.64) -> List[SemanticMatch]:
    model = get_sentence_model()
    if not model or not responsibilities or not job_text:
        return []
    resp_sentences = [r for r in responsibilities if len(r.split()) >= 4][:80]
    job_sentences = sentence_split(job_text)[:120]
    if not resp_sentences or not job_sentences:
        return []
    emb_r = model.encode(resp_sentences, convert_to_tensor=True)
    emb_j = model.encode(job_sentences, convert_to_tensor=True)
    sims = util.cos_sim(emb_r, emb_j)  # (R, J)
    matches: List[SemanticMatch] = []
    for i, r in enumerate(resp_sentences):
        # best job sentence
        row = sims[i]
        j = int(row.argmax())
        sim_val = float(row[j].item())
        if sim_val >= min_similarity:
            matches.append(SemanticMatch(r, job_sentences[j], sim_val))
    return matches


def infer_additional_skills(semantic_matches: List[SemanticMatch], seed_skills: List[str]) -> List[str]:
    skills_lower = {s.lower(): s for s in seed_skills}
    found = []
    for m in semantic_matches:
        sent_low = m.job_sentence.lower()
        for sk_l, orig in skills_lower.items():
            if sk_l in sent_low and orig not in found:
                found.append(orig)
    return found
