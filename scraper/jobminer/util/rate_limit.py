from __future__ import annotations
"""Simple per-host rate limiting helper with backoff & jitter.

Usage:
    from jobminer.util.rate_limit import polite_get
    resp = polite_get("https://api.example.com/data")

Design goals:
 - Lightweight (no external deps)
 - Thread-safe enough for low concurrency (single interpreter GIL)
 - Enforces minimum interval between calls per host (default 0.75s)
 - Adds small random jitter (0–120ms) to avoid lockstep patterns
 - Optional exponential backoff for HTTP 429 or transient 5xx codes

Not automatically wired into existing adapters (kept opt-in to avoid changing
behavior unexpectedly). Adapters can wrap their httpx.get calls with this helper.
"""
import time
import random
import threading
from typing import Optional, Dict, Tuple, Iterable
from urllib.parse import urlparse
import httpx

_LOCK = threading.Lock()
_LAST_CALL: Dict[str, float] = {}


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _sleep_needed(host: str, min_interval: float) -> float:
    now = time.time()
    last = _LAST_CALL.get(host, 0.0)
    delta = now - last
    remaining = min_interval - delta
    return remaining if remaining > 0 else 0.0


def polite_get(url: str, *, min_interval: float = 0.75, timeout: float = 20.0, max_retries: int = 2, backoff_factor: float = 1.8, retry_status: Iterable[int] = (429, 502, 503, 504), client: Optional[httpx.Client] = None, **kwargs):
    host = _host(url)
    attempt = 0
    while True:
        with _LOCK:
            sleep_for = _sleep_needed(host, min_interval)
            if sleep_for > 0:
                # release lock while sleeping to not block other hosts calculations
                pass
        if sleep_for > 0:
            time.sleep(sleep_for + random.uniform(0, 0.12))
        # Perform request
        close_client = False
        if client is None:
            client = httpx.Client(timeout=timeout)
            close_client = True
        try:
            resp = client.get(url, timeout=timeout, **kwargs)
        except httpx.RequestError as e:
            if attempt >= max_retries:
                if close_client:
                    client.close()
                raise
            # treat as retryable similar to 503
            wait = (backoff_factor ** attempt) * 0.5
            time.sleep(wait)
            attempt += 1
            continue
        finally:
            with _LOCK:
                _LAST_CALL[host] = time.time()
        if resp.status_code in retry_status and attempt < max_retries:
            wait = (backoff_factor ** attempt) * 0.75
            time.sleep(wait)
            attempt += 1
            continue
        if close_client:
            client.close()
        return resp
