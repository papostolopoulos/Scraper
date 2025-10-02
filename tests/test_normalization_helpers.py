from scraper.jobminer.normalization import normalize_company, normalize_title, normalize_location


def test_normalize_company_variants():
    assert normalize_company('The Foo, Inc.') == 'foo'
    assert normalize_company('Acme GmbH') == 'acme'
    assert normalize_company('Foo! Bar? LLC') == 'foo bar'


def test_normalize_title_and_location_helpers():
    assert normalize_title('Sr Dev') == 'senior developer'
    assert normalize_title('JR ENG') == 'junior engineer'

    # state expansion and saint/st handling
    assert normalize_location('San Francisco, CA') == 'san francisco california'
    assert normalize_location('Saint Louis, MO') == 'st louis mo'
