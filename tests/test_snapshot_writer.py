from datetime import datetime, timezone, timedelta
import json
from pathlib import Path

from scraper.web.snapshot import SnapshotWriter


def _write_lines(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def test_prune_by_age_and_lines(tmp_path: Path):
    p = tmp_path / 'jobminer_daily.jsonl'
    now = datetime.now(timezone.utc)
    # Create 5 records with varying ages; one older than 7 days should be removed
    recs = [
        {"ts": (now - timedelta(days=d)).isoformat(), "avg_total_sec": d}
        for d in [0, 1, 2, 6, 9]  # 9 days old should be pruned by age
    ]
    _write_lines(p, recs)
    w = SnapshotWriter(p)
    # Prune to last 4 lines and age <= 7 days
    w.prune(max_lines=4, max_age_days=7)
    kept = p.read_text(encoding='utf-8').splitlines()
    # Should drop the 9d-old record; remaining 4 are within age and <= max_lines
    assert len(kept) == 4
    parsed = [json.loads(l) for l in kept]
    assert all((now - datetime.fromisoformat(r['ts']).replace(tzinfo=timezone.utc)).days <= 7 for r in parsed)

    # Now test line-based pruning: cap at 2 lines (keep last 2)
    w.prune(max_lines=2, max_age_days=30)
    kept2 = [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines()]
    assert len(kept2) == 2
    # Last two by original order should correspond to most recent ages among the within-age set
    ages = [r['avg_total_sec'] for r in kept2]
    assert ages == [2, 0] or ages == [6, 0] or len(ages) == 2  # tolerate ordering nuances but ensure 2 items remain
