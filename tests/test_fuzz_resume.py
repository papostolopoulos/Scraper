import os
from pathlib import Path
import io
import random
import string
import tempfile

import pytest
from hypothesis import given, settings, strategies as st

from scraper.jobminer import resume


# Strategy to build synthetic 'PDF-like' text: we won't create a real PDF binary (pypdf expects one),
# so we instead monkeypatch extract_text to bypass actual PDF parsing for fuzzing. This keeps the
# fuzz test fast and avoids heavy binary generation.

HEADER_LINES = [
    "PROFESSIONAL SUMMARY", "AREAS OF EXPERTISE", "TECHNICAL SKILLS", "WORK EXPERIENCE",
    "EDUCATION", "CERTIFICATIONS"
]

verbs = [
    "Led", "Managed", "Improved", "Reduced", "Designed", "Implemented", "Coordinated",
    "Built", "Developed", "Engineered", "Validated", "Launched", "Optimized"
]

word_chars = string.ascii_letters + string.digits + "+#.-"

def rand_token(min_len=2, max_len=12):
    return ''.join(random.choice(word_chars) for _ in range(random.randint(min_len, max_len)))

@st.composite
def resume_texts(draw):
    # Random counts
    n_expertise = draw(st.integers(min_value=0, max_value=10))
    n_tech = draw(st.integers(min_value=0, max_value=25))
    n_resp = draw(st.integers(min_value=0, max_value=30))

    expertise_items = [rand_token().title() for _ in range(n_expertise)]
    tech_items = [rand_token().upper() for _ in range(n_tech)]
    resp_lines = []
    for _ in range(n_resp):
        verb = random.choice(verbs)
        tail_words = [rand_token() for _ in range(random.randint(3, 10))]
        resp_lines.append(f"• {verb} {' '.join(tail_words)}.")

    lines = []
    # Optional headers
    if expertise_items:
        lines.append("AREAS OF EXPERTISE")
        # pipe separated variant
        chunk = " | ".join(expertise_items)
        lines.append(chunk)
    if tech_items:
        lines.append("TECHNICAL SKILLS")
        lines.append(", ".join(tech_items))
    if resp_lines:
        lines.append("WORK EXPERIENCE")
        lines.extend(resp_lines)
    # Sometimes add unrelated noise and random casing
    noise_blocks = draw(st.lists(st.text(min_size=0, max_size=40), min_size=0, max_size=5))
    for nb in noise_blocks:
        if nb:
            lines.append(nb)
    text = "\n".join(lines)
    # Seed skills derived from mixture of tokens
    seed_pool = expertise_items[:5] + tech_items[:5]
    seed_skills = list(dict.fromkeys(seed_pool))
    return text, seed_skills


@pytest.fixture()
def fake_pdf(tmp_path):
    # Create a dummy file path (not a real PDF). We'll intercept extract_text.
    p = tmp_path / "resume.pdf"
    p.write_bytes(b"%PDF-1.4\n%Fake minimal placeholder\n")
    return p


@given(resume_texts())
@settings(max_examples=60, deadline=500)
def test_fuzz_build_resume_profile(monkeypatch, fake_pdf, data):
    text, seed_skills = data

    # Monkeypatch extract_text to return our synthetic text regardless of file content
    monkeypatch.setattr(resume, 'extract_text', lambda _: text)

    prof = resume.build_resume_profile(fake_pdf, seed_skills)

    # Invariants:
    # 1. No crash and returns ResumeProfile
    assert isinstance(prof, resume.ResumeProfile)
    # 2. Skills list has no duplicates and each element is non-empty short-ish string
    assert len(prof.skills) == len(set(prof.skills))
    for s in prof.skills:
        assert isinstance(s, str)
        assert 1 <= len(s) <= 100
    # 3. Summary length bounded
    assert len(prof.summary) <= 1500
    # 4. Responsibilities each within size bounds and not uppercase-only
    for r in prof.responsibilities:
        assert 15 <= len(r) <= 220
        assert not r.isupper()
    # 5. Idempotence: second build with same seed returns identical aggregated skills (order preserved)
    prof2 = resume.build_resume_profile(fake_pdf, seed_skills)
    assert prof.skills == prof2.skills
    # 6. If seed skills provided, any seed skill present must appear at most once
    for sk in seed_skills:
        assert prof.skills.count(sk) <= 1


def test_cache_roundtrip(monkeypatch, fake_pdf):
    # Simple deterministic text to verify cache hit path
    monkeypatch.setattr(resume, 'extract_text', lambda _: "WORK EXPERIENCE\n• Led System Refactor.")
    seed = ["Python", "SQL"]
    prof1 = resume.load_or_build_resume_profile(fake_pdf, seed, force_rebuild=True)
    prof2 = resume.load_or_build_resume_profile(fake_pdf, seed, force_rebuild=False)
    assert prof1.skills == prof2.skills
    # Force rebuild changes nothing semantically
    prof3 = resume.load_or_build_resume_profile(fake_pdf, seed, force_rebuild=True)
    assert prof1.skills == prof3.skills
