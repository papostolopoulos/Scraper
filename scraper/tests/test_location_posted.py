from datetime import date
from scraper.jobminer.collector import derive_location_from_description, parse_posted_text


def test_derive_location_from_description():
    desc = """We are a distributed team.
This role is based in Barcelona, Spain and collaborates globally.
Responsibilities include building data pipelines."""
    loc = derive_location_from_description(desc)
    assert loc.lower().startswith('barcelona')


def test_parse_posted_text_relative():
    d = parse_posted_text('Posted 3 days ago')
    assert isinstance(d, date)


def test_parse_posted_text_absolute():
    d = parse_posted_text('Posted on August 5, 2025')
    assert d == date(2025, 8, 5)
