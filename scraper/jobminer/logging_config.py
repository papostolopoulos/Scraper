from __future__ import annotations
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
import json
from datetime import datetime, timezone

LOG_DIR = Path(__file__).resolve().parent.parent / 'logs'

STRUCTURED_LOG_FILE = LOG_DIR / 'collector.events.jsonl'

_DEF_FORMAT = '%(asctime)s %(levelname)s %(name)s %(message)s'


DISABLE_FILE_LOGS = bool(os.getenv('SCRAPER_DISABLE_FILE_LOGS'))
DISABLE_EVENTS = bool(os.getenv('SCRAPER_DISABLE_EVENTS'))

def setup_logging(debug: bool = False):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if root.handlers:
        # already configured
        return
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    if not DISABLE_FILE_LOGS:
        # human readable rotating log
        fh = RotatingFileHandler(LOG_DIR / 'collector.log', maxBytes=1_000_000, backupCount=5, encoding='utf-8')
        fh.setFormatter(logging.Formatter(_DEF_FORMAT))
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
    if debug:
        ch.setLevel(logging.DEBUG)
    else:
        ch.setLevel(logging.INFO)
    if not DISABLE_FILE_LOGS:
        root.addHandler(fh)  # type: ignore[name-defined]
    root.addHandler(ch)
    logging.getLogger('playwright').setLevel(logging.WARNING)


def log_event(event: str, **fields):
    """Append a structured JSON event line."""
    if DISABLE_EVENTS:
        return
    try:
        with STRUCTURED_LOG_FILE.open('a', encoding='utf-8') as f:
            rec = {'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'event': event}
            rec.update(fields)
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    except Exception:
        logging.getLogger(__name__).debug('Failed to write structured log line', exc_info=True)
