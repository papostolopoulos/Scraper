from pathlib import Path
from scraper.jobminer.comp_norm import load_comp_config, load_benefit_mappings, convert_salary, map_benefits

def test_convert_salary_basic(tmp_path):
    # Write minimal config
    cfg_dir = tmp_path / 'config'
    cfg_dir.mkdir()
    (cfg_dir / 'compensation.yml').write_text('base_currency: USD\ncurrency_rates:\n  EUR: 1.1\n', encoding='utf-8')
    cfg = load_comp_config(tmp_path)
    mn, mx = convert_salary(50000, 70000, 'EUR', 'yearly', cfg)
    assert mn == 55000.0 and mx == 77000.0


def test_convert_salary_unknown_currency(tmp_path):
    cfg = load_comp_config(tmp_path)
    mn, mx = convert_salary(100, 200, 'XYZ', 'yearly', cfg)
    assert mn is None and mx is None


def test_benefit_mapping(tmp_path):
    cfg_dir = tmp_path / 'config'
    cfg_dir.mkdir()
    (cfg_dir / 'benefits.yml').write_text('mappings:\n  health: ["health insurance","medical"]\n  remote: ["remote work"]\n', encoding='utf-8')
    mapping = load_benefit_mappings(tmp_path)
    out = map_benefits(['Great Health Insurance plan', 'Remote Work anywhere'], mapping)
    assert out == ['health', 'remote']
