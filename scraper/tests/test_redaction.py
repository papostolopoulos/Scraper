from pathlib import Path
from scraper.jobminer.redaction import load_redaction_config, redact_text, redact_fields

def test_redact_text_email(tmp_path):
    cfg_dir = tmp_path / 'config'
    cfg_dir.mkdir()
    (cfg_dir / 'redaction.yml').write_text('enabled: true\nrules:\n  email: "[A-Za-z]+@[A-Za-z]+\\.[A-Za-z]{2,}"\nreplacement: "XXX"\n', encoding='utf-8')
    cfg = load_redaction_config(tmp_path)
    assert redact_text('Contact me at test@example.com today', cfg) == 'Contact me at XXX today'


def test_redact_fields(tmp_path):
    cfg = load_redaction_config(tmp_path)  # defaults on
    rec = {'title': 'Engineer', 'apply_url': 'https://example.com/apply'}
    out = redact_fields(rec, ['apply_url'], cfg)
    assert out['apply_url'] == '[REDACTED]'
