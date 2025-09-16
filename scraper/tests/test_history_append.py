from pathlib import Path
import tempfile, json
from scraper.jobminer.history import append_history


def test_history_append_increments_lines():
    with tempfile.TemporaryDirectory() as td:
        history = Path(td) / 'hist.jsonl'
        summary = {'collected_total':1,'new_total':1}
        append_history(summary, history)
        append_history(summary, history)
        lines = history.read_text(encoding='utf-8').strip().splitlines()
        assert len(lines) == 2
        rec = json.loads(lines[0])
        assert 'timestamp_utc' in rec
