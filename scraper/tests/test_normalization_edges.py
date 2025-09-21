from scraper.jobminer.normalization import normalize_company, normalize_title, normalize_location

def test_company_suffix_and_the_stripped():
    assert normalize_company('The Acme, Inc.') == 'acme'
    assert normalize_company('Acme LLC') == 'acme'

def test_title_abbreviations():
    assert normalize_title('Sr Data Eng') == 'senior data engineer'
    assert normalize_title('JR DEV') == 'junior developer'

def test_location_state_expansion_and_street():
    # state expansion
    assert normalize_location('San Francisco, CA') == 'san francisco california'
    # saint/st handling
    assert normalize_location('Saint Louis, MO') == 'st louis mo'
