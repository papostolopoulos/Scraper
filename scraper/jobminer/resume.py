from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Tuple
import re
from pypdf import PdfReader
import json, hashlib, os, time

SKILL_SPLIT = re.compile(r"[,/;\n]\s*")

class ResumeProfile:
    def __init__(self, raw_text: str, skills: List[str], summary: str,
                 expertise: List[str], technical: List[str], responsibilities: List[str]):
        self.raw_text = raw_text
        self.skills = skills  # aggregated canonical skill/keyword list
        self.summary = summary
        self.expertise = expertise
        self.technical = technical
        self.responsibilities = responsibilities
    # simple dict serialization (raw_text kept – could be large, acceptable for single profile)
    def to_dict(self):
        return {
            'raw_text': self.raw_text,
            'skills': self.skills,
            'summary': self.summary,
            'expertise': self.expertise,
            'technical': self.technical,
            'responsibilities': self.responsibilities,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'ResumeProfile':
        return cls(
            d.get('raw_text',''), d.get('skills',[]), d.get('summary',''),
            d.get('expertise',[]), d.get('technical',[]), d.get('responsibilities',[])
        )


def extract_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    text = []
    for page in reader.pages:
        text.append(page.extract_text() or "")
    return "\n".join(text)


SECTION_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("professional_summary", re.compile(r"^\s*professional summary\b", re.I)),
    ("areas_of_expertise", re.compile(r"^\s*areas of expertise\b", re.I)),
    # Some resumes embed expertise inline after title lines; we also treat a line of many pipes as expertise continuation
    ("technical_skills", re.compile(r"^\s*(technical skills|technical skills and tools|technical tools|program management \|)", re.I)),
    ("work_experience", re.compile(r"^\s*work experience\b", re.I)),
]

def parse_sections(text: str) -> Dict[str, List[str]]:
    lines = [l.rstrip() for l in text.splitlines()]
    sections: Dict[str, List[str]] = {k: [] for k, _ in SECTION_PATTERNS}
    current = None
    for line in lines:
        header_found = False
        for key, pat in SECTION_PATTERNS:
            if pat.search(line):
                current = key
                header_found = True
                break
        if header_found:
            continue
        # Heuristic: lines with >=3 pipes likely part of expertise list
        if current is None and line.count('|') >= 3:
            current = 'areas_of_expertise'
        # Stop at EDUCATION / CERTIFICATIONS style headings
        if re.match(r"^\s*(education|certifications|projects)\b", line, re.I):
            current = None
            continue
        if current:
            sections[current].append(line)
    return sections

TECH_TOKEN_RGX = re.compile(r"^[A-Za-z0-9+.#-]{2,40}$")

def extract_expertise_terms(raw_lines: List[str]) -> List[str]:
    # Only consider pipe-separated fragments (explicitly enumerated expertise areas)
    pipe_frags = []
    for l in raw_lines:
        if '|' in l:
            pipe_frags.extend([p.strip() for p in l.split('|') if p.strip()])
    text = ", ".join(pipe_frags)
    parts = re.split(r"[,;]\s*", text)
    out = []
    for p in parts:
        t = p.strip().strip('-•').strip()
        if not (2 <= len(t) <= 60) or '  ' in t:
            continue
        # reject long sentence fragments (multiple spaces or verbs likely)
        words = t.split()
        if len(words) > 5:
            continue
        # reject common stop words
        if t.lower() in {"and","the","with","including","across","track record","teams"}:
            continue
        # require at least one uppercase letter (proper noun / acronym) or be multi-word tech concept
        if not any(c.isupper() for c in t if c.isalpha()) and len(words) <= 1:
            continue
        out.append(t)
    return list(dict.fromkeys(out))

def extract_technical_terms(raw_lines: List[str]) -> List[str]:
    if not raw_lines:
        return []
    text = " ".join(raw_lines)
    parts = re.split(r"[,;|]\s*", text)
    out = []
    for p in parts:
        t = p.strip().strip('-•').strip()
        if not t:
            continue
        if len(t) > 50:
            continue
        # Must contain a letter and be alphanumeric/punct token typical of tools/technologies
        if not re.search(r"[A-Za-z]", t):
            continue
        out.append(t)
    return list(dict.fromkeys(out))

def extract_responsibility_phrases(raw_lines: List[str]) -> List[str]:
    out = []
    buffer = []
    for line in raw_lines:
        ln = line.rstrip()
        if not ln:
            continue
        bullet = False
        if re.match(r"^[\u2022\-o ]{0,3}[A-Za-z]", ln):
            # treat new phrase start when line starts with bullet char or small prefix then letter
            if buffer:
                phrase = ' '.join(buffer).strip('•- o')
                if 15 <= len(phrase) <= 220:
                    out.append(phrase)
                buffer = []
            bullet = True
        buffer.append(ln)
    if buffer:
        phrase = ' '.join(buffer).strip('•- o')
        if 15 <= len(phrase) <= 220:
            out.append(phrase)
    return out

def fallback_responsibilities(all_text: str) -> List[str]:
    lines = [l.rstrip() for l in all_text.splitlines()]
    bullets = []
    for l in lines:
        ls = l.strip()
        # treat all-caps headings differently; skip them
        if not ls:
            continue
        if ls.isupper() and len(ls.split()) < 8:
            continue
        if len(ls.split()) > 4 and not ls.endswith((':',';')):
            # consider as a potential responsibility style sentence if contains a verb + object
            if any(v in ls.lower() for v in (' led ',' managed ',' reduced ',' improved ',' designed ',' implemented ',' coordinated ',' supported ',' oversaw ',' built ',' engineered ',' validated ',' authored ',' developed ')):
                bullets.append(ls)
    if len(bullets) >= 5:
        return bullets[:120]
    # heuristic: sentences starting with action verbs
    verbs = {'led','managed','drove','reduced','improved','designed','implemented','coordinated','secured','authored','developed','supported','oversaw','built','engineered','validated'}
    import re as _re
    sentences = _re.split(r"(?<=[.!?])\s+", all_text)
    out2 = []
    for s in sentences:
        w = s.strip().split()
        if len(w) >= 5 and w[0].lower().strip('•-') in verbs:
            out2.append(s.strip())
    return (bullets + out2)[:120]

def heuristic_responsibilities(full_text: str) -> List[str]:
    # Extract sentences from WORK EXPERIENCE block emphasizing action verbs and impact
    block_match = re.search(r"WORK EXPERIENCE(.+?)(EDUCATION|CERTIFICATIONS|PROJECTS|$)", full_text, re.I | re.S)
    if block_match:
        block = block_match.group(1)
    else:
        block = full_text
    sentences = re.split(r"(?<=[.!?])\s+", block)
    verbs = {'led','managed','reduced','improved','designed','implemented','coordinated','supported','oversaw','built','engineered','validated','authored','developed','increased','decreased','drove','streamlined','optimized','launched'}
    out = []
    for s in sentences:
        st = s.strip()
        if not st:
            continue
        words = st.split()
        if not (7 <= len(words) <= 60):
            continue
        lower = st.lower()
        if any(lower.startswith(v + ' ') for v in verbs) or any((' ' + v + ' ') in lower for v in verbs):
            if st.isupper():
                continue
            out.append(st)
        if len(out) >= 120:
            break
    return out

def build_aggregated_skills(sections: Dict[str, List[str]], seed_skills: List[str], full_text: str) -> List[str]:
    seed_lower = {s.lower(): s for s in seed_skills}
    expertise = extract_expertise_terms(sections.get('areas_of_expertise', []))
    technical = extract_technical_terms(sections.get('technical_skills', []))
    if not technical:
        # Derive technical list heuristically from expertise tokens that look like tools/tech
        derived = [t for t in expertise if re.search(r"[A-Za-z]", t) and any(ch.isalpha() for ch in t)]
        technical = derived[:40]
    responsibilities = extract_responsibility_phrases(sections.get('work_experience', []))
    if not responsibilities:
        responsibilities = fallback_responsibilities(full_text)
    if not responsibilities:
        responsibilities = heuristic_responsibilities(full_text)
    # Collect tokens from responsibilities that are in seed skills
    resp_tokens = set()
    for phrase in responsibilities:
        for tok in re.findall(r"[A-Za-z0-9+.#-]+", phrase):
            tl = tok.lower()
            if tl in seed_lower:
                resp_tokens.add(seed_lower[tl])
    aggregated = []
    def add(items):
        for it in items:
            if it and it not in aggregated:
                aggregated.append(it)
    # Prioritize explicit technical, then expertise tokens filtered
    add(technical)
    add(expertise)
    add(sorted(resp_tokens))
    # fallback: if still too small, include seed skills found anywhere in summary or sections
    if len(aggregated) < 5:
        joined = "\n".join(sum(sections.values(), []))
        lower = joined.lower()
        for sk in seed_skills:
            if sk.lower() in lower and sk not in aggregated:
                aggregated.append(sk)
    return aggregated


def build_resume_profile(pdf_path: Path, seed_skills: List[str]) -> ResumeProfile:
    text = extract_text(pdf_path)
    sections = parse_sections(text)
    # Professional summary: join first 8 lines or fallback to first 1200 chars
    summary_lines = sections.get('professional_summary') or text.splitlines()[:15]
    summary = " ".join(l.strip() for l in summary_lines)[:1500]
    expertise = extract_expertise_terms(sections.get('areas_of_expertise', []))
    technical = extract_technical_terms(sections.get('technical_skills', []))
    responsibilities = extract_responsibility_phrases(sections.get('work_experience', []))
    if not responsibilities:
        responsibilities = fallback_responsibilities(text)
    if not responsibilities:
        responsibilities = heuristic_responsibilities(text)
    aggregated = build_aggregated_skills(sections, seed_skills, text)
    return ResumeProfile(text, aggregated, summary, expertise, technical, responsibilities)

# ---------------- Cache Layer ----------------
_CACHE_VERSION = 1

# Memoize PDF hash by (path, size, mtime_ns) to avoid re-reading large file each cached load
_PDF_HASH_CACHE: dict[tuple[str, int, int], str] = {}

def _cache_dir() -> Path:
    return Path(__file__).resolve().parent / 'data'

def get_resume_profile_cache_path() -> Path:
    return _cache_dir() / 'resume_profile_cache.json'

def _sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()

def _pdf_hash(pdf_path: Path) -> str:
    try:
        st = pdf_path.stat()
        key = (str(pdf_path), st.st_size, getattr(st, 'st_mtime_ns', int(st.st_mtime * 1e9)))
        cached = _PDF_HASH_CACHE.get(key)
        if cached:
            return cached
        h = _sha1_bytes(pdf_path.read_bytes())
        # keep cache small (only current resume expected). If grows, trim.
        if len(_PDF_HASH_CACHE) > 8:
            _PDF_HASH_CACHE.clear()
        _PDF_HASH_CACHE[key] = h
        return h
    except Exception:
        return ''

def _seed_hash(seed_skills: List[str]) -> str:
    joined = '\n'.join(seed_skills)
    return _sha1_bytes(joined.encode('utf-8')) if joined else ''

def load_cached_resume_profile(pdf_path: Path, seed_skills: List[str]) -> ResumeProfile | None:
    """Return cached profile if present & matching hashes/version."""
    cache_file = get_resume_profile_cache_path()
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text(encoding='utf-8'))
    except Exception:
        return None
    if data.get('version') != _CACHE_VERSION:
        return None
    if data.get('pdf_hash') != _pdf_hash(pdf_path):
        return None
    if data.get('seed_hash') != _seed_hash(seed_skills):
        return None
    prof = data.get('profile') or {}
    try:
        return ResumeProfile.from_dict(prof)
    except Exception:
        return None

def save_cached_resume_profile(pdf_path: Path, seed_skills: List[str], profile: ResumeProfile) -> None:
    cache_file = get_resume_profile_cache_path()
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'version': _CACHE_VERSION,
            'pdf_hash': _pdf_hash(pdf_path),
            'seed_hash': _seed_hash(seed_skills),
            'created_ts': time.time(),
            'profile': profile.to_dict(),
        }
        cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass  # cache failures are non-fatal

def load_or_build_resume_profile(pdf_path: Path, seed_skills: List[str], force_rebuild: bool | None = None) -> ResumeProfile:
    """Load resume profile from cache, else build & store.
    Set force_rebuild=True to ignore cache (also via env SCRAPER_REBUILD_RESUME_PROFILE=1).
    """
    if force_rebuild is None:
        force_rebuild = os.environ.get('SCRAPER_REBUILD_RESUME_PROFILE') == '1'
    if not force_rebuild:
        cached = load_cached_resume_profile(pdf_path, seed_skills)
        if cached:
            return cached
    prof = build_resume_profile(pdf_path, seed_skills)
    save_cached_resume_profile(pdf_path, seed_skills, prof)
    return prof
