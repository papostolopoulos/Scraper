from datetime import date
from scraper.jobminer.collector import parse_posted_text

def test_parse_posted_text_absolute():
    d = parse_posted_text("Posted on September 12, 2025")
    assert isinstance(d, date)
    assert d.year == 2025 and d.month == 9 and d.day == 12

def test_parse_posted_text_relative():
    d = parse_posted_text("3 days ago")
    assert isinstance(d, date)
