import random, string
from scraper.jobminer.enrich import parse_location


def random_token():
    return ''.join(random.choice(string.ascii_letters) for _ in range(random.randint(3,10)))


def test_parse_location_remote_detection():
    loc, meta = parse_location('Fully Remote across USA')
    assert loc == 'Remote'
    assert meta and meta.get('mode_hint') == 'remote'


def test_parse_location_fuzz_no_exception():
    for _ in range(50):
        s = ', '.join(random_token() for _ in range(random.randint(1,4)))
        loc, meta = parse_location(s)
        # Should always return a canonical or original string, never raise
        assert loc is None or isinstance(loc, str)
        # meta may be None if loc None
