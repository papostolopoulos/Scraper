from pathlib import Path
import os
from scraper.jobminer.compliance import automation_allowed

def test_compliance_cli_flag(tmp_path, monkeypatch):
    assert automation_allowed(tmp_path, cli_flag=True) is True
    assert automation_allowed(tmp_path, cli_flag=False) is False

def test_compliance_env(tmp_path, monkeypatch):
    monkeypatch.setenv('SCRAPER_ALLOW_AUTOMATION', '1')
    assert automation_allowed(tmp_path) is True
    monkeypatch.setenv('SCRAPER_ALLOW_AUTOMATION', '0')
    assert automation_allowed(tmp_path) is False

def test_compliance_config(tmp_path):
    cfg_dir = tmp_path / 'config'
    cfg_dir.mkdir()
    (cfg_dir / 'compliance.yml').write_text('allow_automation: true\n', encoding='utf-8')
    assert automation_allowed(tmp_path) is True
    (cfg_dir / 'compliance.yml').write_text('allow_automation: false\n', encoding='utf-8')
    assert automation_allowed(tmp_path) is False
