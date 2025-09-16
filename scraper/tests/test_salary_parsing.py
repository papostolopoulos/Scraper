from scraper.jobminer.collector import extract_salary

# Each case: (text, expected_period)
CASES = [
    ("Compensation: $100k - $120k per year", 'year'),
    ("Earn $50 - $60 per hour depending on experience", 'year'),
    ("Salary range EUR 4000 - 5000 per month", 'year'),
    ("Daily rate £300 - £400 per day", 'year'),
    ("Pay: $85k", 'year'),
]

def test_extract_salary_periods():
    for text, period in CASES:
        min_a, max_a, cur, p, raw = extract_salary(text)
        assert p == period, f"Expected period {period} got {p} for text {text}"
        assert raw is not None
        if min_a and max_a:
            assert max_a >= min_a


def test_extract_salary_none():
    min_a, max_a, cur, p, raw = extract_salary("No salary info here")
    assert all(x is None for x in [min_a, max_a, cur, p, raw])
