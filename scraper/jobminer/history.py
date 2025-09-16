"""Run history logging utilities.

Writes each pipeline summary as one JSON line (JSONL) for easy append and later analysis.
File lives under data/exports by default (configurable via CLI flag).
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json
from typing import Dict, Any

def append_history(summary: Dict[str, Any], history_path: Path):
    history_path.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(summary)
    rec['timestamp_utc'] = datetime.now(timezone.utc).isoformat()
    try:
        with history_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    except Exception:
        # Non-fatal; ignore failures
        pass

__all__ = ['append_history']