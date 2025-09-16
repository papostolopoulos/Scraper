from __future__ import annotations
import os, textwrap, tempfile, shutil
from pathlib import Path
import pytest
from scraper.jobminer.weights import load_weights


def write_yaml(tmp: Path, content: str) -> Path:
    p = tmp / 'w.yml'
    p.write_text(textwrap.dedent(content), encoding='utf-8')
    return p

def test_weights_valid(monkeypatch, tmp_path: Path):
    f = write_yaml(tmp_path, """
    weights:
      skill: 0.4
      semantic: 0.3
      recency: 0.15
      seniority: 0.1
      company: 0.05
    thresholds:
      shortlist: 0.7
      review: 0.5
    """)
    monkeypatch.setenv('SCRAPER_WEIGHTS_FILE', str(f))
    w, t = load_weights(force_reload=True)
    assert w['skill'] == 0.4 and t['shortlist'] == 0.7

def test_weights_missing_key(monkeypatch, tmp_path: Path):
    f = write_yaml(tmp_path, """
    weights:
      skill: 0.4
      semantic: 0.3
      recency: 0.15
      seniority: 0.1
    thresholds:
      shortlist: 0.7
      review: 0.5
    """)
    monkeypatch.setenv('SCRAPER_WEIGHTS_FILE', str(f))
    with pytest.raises(ValueError) as e:
        load_weights(force_reload=True)
    assert 'missing weight keys' in str(e.value)

def test_weights_negative(monkeypatch, tmp_path: Path):
    f = write_yaml(tmp_path, """
    weights:
      skill: -0.4
      semantic: 0.3
      recency: 0.15
      seniority: 0.1
      company: 0.05
    thresholds:
      shortlist: 0.7
      review: 0.5
    """)
    monkeypatch.setenv('SCRAPER_WEIGHTS_FILE', str(f))
    with pytest.raises(ValueError) as e:
        load_weights(force_reload=True)
    assert 'must be > 0' in str(e.value)

def test_weights_total_range(monkeypatch, tmp_path: Path):
    # total too small
    f_small = write_yaml(tmp_path, """
    weights:
      skill: 0.1
      semantic: 0.1
      recency: 0.1
      seniority: 0.1
      company: 0.1
    thresholds:
      shortlist: 0.7
      review: 0.5
    """)
    monkeypatch.setenv('SCRAPER_WEIGHTS_FILE', str(f_small))
    with pytest.raises(ValueError):
        load_weights(force_reload=True)
    # total too large
    f_large = write_yaml(tmp_path, """
    weights:
      skill: 0.9
      semantic: 0.35
      recency: 0.15
      seniority: 0.15
      company: 0.1
    thresholds:
      shortlist: 0.7
      review: 0.5
    """)
    monkeypatch.setenv('SCRAPER_WEIGHTS_FILE', str(f_large))
    with pytest.raises(ValueError):
        load_weights(force_reload=True)

def test_threshold_relation(monkeypatch, tmp_path: Path):
    f = write_yaml(tmp_path, """
    weights:
      skill: 0.4
      semantic: 0.3
      recency: 0.15
      seniority: 0.1
      company: 0.05
    thresholds:
      shortlist: 0.4
      review: 0.5
    """)
    monkeypatch.setenv('SCRAPER_WEIGHTS_FILE', str(f))
    with pytest.raises(ValueError) as e:
        load_weights(force_reload=True)
    assert 'threshold relation' in str(e.value)
