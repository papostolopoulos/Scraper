from hypothesis import given, strategies as st, settings
from scraper.jobminer.skills import extract_skills, extract_resume_overlap_skills

# Strategy for synthetic descriptions: words + punctuation tokens mixing tech and noise
tech_tokens = st.sampled_from([
    'python','sql','kubernetes','docker','aws','azure','gcp','spark','pandas','numpy','scala','terraform','airflow','linux','git','ci','cd','ml','data','analysis','cloud','infrastructure','pipeline'
])
noise_tokens = st.text(min_size=1, max_size=8).filter(lambda s: s.isalpha())
word = st.one_of(tech_tokens, noise_tokens)

descriptions = st.lists(word, min_size=0, max_size=120).map(lambda lst: ' '.join(lst))
seed_skill_lists = st.lists(tech_tokens, min_size=1, max_size=15, unique=True)

@given(descriptions, seed_skill_lists)
@settings(max_examples=60, deadline=None)
def test_extract_skills_deterministic(desc, seeds):
    r1 = extract_skills(desc, seeds)
    r2 = extract_skills(desc, seeds)
    assert r1 == r2

@given(descriptions, seed_skill_lists)
@settings(max_examples=50, deadline=None)
def test_extract_skills_no_empty(desc, seeds):
    out = extract_skills(desc, seeds)
    assert all(s.strip() for s in out)

@given(descriptions, seed_skill_lists)
@settings(max_examples=40, deadline=None)
def test_extract_skills_subset_of_seeds(desc, seeds):
    out = extract_skills(desc, seeds)
    # All outputs must be from seeds exactly
    assert set(out).issubset(set(seeds))

@given(descriptions, seed_skill_lists)
@settings(max_examples=40, deadline=None)
def test_overlap_subset(desc, seeds):
    overlap = extract_resume_overlap_skills(desc, seeds)
    assert set(overlap).issubset(set(seeds))

@given(descriptions, seed_skill_lists)
@settings(max_examples=30, deadline=None)
def test_idempotence(desc, seeds):
    out = extract_skills(desc, seeds)
    # Running again on joined output shouldn't add new or change order
    out2 = extract_skills(' '.join(desc.split()+out), seeds)
    assert out == [s for s in out2 if s in out]
