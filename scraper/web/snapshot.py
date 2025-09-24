import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

SNAPSHOT_DIR = Path(os.getenv("JOBMINER_SNAPSHOT_DIR", "snapshots"))
SNAPSHOT_DIR.mkdir(exist_ok=True)

SNAPSHOT_FILE = SNAPSHOT_DIR / "jobminer_daily.jsonl"

class SnapshotWriter:
    def __init__(self, path=SNAPSHOT_FILE):
        self.path = Path(path)

    def append(self, data: Dict[str, Any]):
        data = dict(data)
        data['ts'] = datetime.now(timezone.utc).isoformat()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data, default=str) + "\n")

    def read_recent(self, max_lines=100):
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(l) for l in lines[-max_lines:]]

    def prune(self, max_lines=5000, max_age_days=7):
        if not self.path.exists():
            return
        lines = self.path.read_text(encoding="utf-8").splitlines()
        now = datetime.now(timezone.utc)
        kept = []
        for l in lines:
            try:
                d = json.loads(l)
                ts = d.get('ts')
                if ts:
                    dt = datetime.fromisoformat(ts)
                    if (now - dt).days <= max_age_days:
                        kept.append(l)
            except Exception:
                continue
        if len(kept) > max_lines:
            kept = kept[-max_lines:]
        self.path.write_text("\n".join(kept), encoding="utf-8")
