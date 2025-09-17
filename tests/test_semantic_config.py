import os
from pathlib import Path
from scraper.jobminer.semantic_enrich import SemanticEnricher


def test_semantic_config_file(tmp_path, monkeypatch):
    cfg = tmp_path / 'config' / 'semantic.yml'
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text('similarity_threshold: 0.9\nmax_new: 1\nenable_bigrams: false\n', encoding='utf-8')
    enr = SemanticEnricher(config_root=tmp_path)
    # With high threshold, nothing should be added
    out = enr.enrich('python sql etl engineer role', ['python'], ['python','sql','etl'])
    assert out == ['python']


def test_semantic_env_overrides(monkeypatch):
    # Force permissive threshold and small cap via env
    monkeypatch.setenv('SCRAPER_SEMANTIC_THRESHOLD', '0.0')
    monkeypatch.setenv('SCRAPER_SEMANTIC_MAX_NEW', '1')
    monkeypatch.setenv('SCRAPER_SEMANTIC_ENABLE_BIGRAMS', '0')
    enr = SemanticEnricher()
    out = enr.enrich('python sql etl engineer role', ['python'], ['python','sql','etl'])
    # Only one new item should be added due to cap=1
    assert len(out) == 2
    assert 'python' in out