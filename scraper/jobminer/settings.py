"""Centralized settings with environment + runtime config overlay.
Provides typed accessors to avoid scattering magic numbers.
"""
from __future__ import annotations
from pathlib import Path
import os, yaml
from dataclasses import dataclass

_RUNTIME_CACHE: dict | None = None

CONFIG_DIR = Path(__file__).resolve().parent.parent / 'config'

def _load_runtime() -> dict:
    global _RUNTIME_CACHE
    if _RUNTIME_CACHE is None:
        cfg_file = CONFIG_DIR / 'runtime.yml'
        if cfg_file.exists():
            try:
                _RUNTIME_CACHE = yaml.safe_load(cfg_file.read_text(encoding='utf-8')) or {}
            except Exception:
                _RUNTIME_CACHE = {}
        else:
            _RUNTIME_CACHE = {}
    return _RUNTIME_CACHE

def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is not None:
        try:
            return float(v)
        except ValueError:
            return default
    return float(_load_runtime().get(name.lower(), default))

def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is not None:
        try:
            return int(v)
        except ValueError:
            return default
    return int(_load_runtime().get(name.lower(), default))

def _env_str(name: str, default: str) -> str:
    v = os.getenv(name)
    if v is not None:
        return v
    return str(_load_runtime().get(name.lower(), default))

SCHEMA_VERSION = 2  # increment when schema changes requiring migration logic (v2 adds status_history table)

@dataclass(frozen=True)
class Settings:
    polite_min: float
    polite_max: float
    location_retry_first_delay: float
    location_retry_second_delay: float
    skill_cache_max_entries: int
    skill_cache_max_disk_mb: int
    metrics_output_path: Path

def load_settings() -> Settings:
    return Settings(
        polite_min=_env_float('SCRAPER_POLITE_MIN', 1.0),
        polite_max=_env_float('SCRAPER_POLITE_MAX', 2.5),
        location_retry_first_delay=_env_float('SCRAPER_LOCATION_RETRY1', 0.6),
        location_retry_second_delay=_env_float('SCRAPER_LOCATION_RETRY2', 1.2),
        skill_cache_max_entries=_env_int('SCRAPER_SKILL_CACHE_MAX_ENTRIES', 500),
        skill_cache_max_disk_mb=_env_int('SCRAPER_SKILL_CACHE_MAX_MB', 8),
        metrics_output_path=Path(os.getenv('SCRAPER_RUN_SUMMARY', 'scraper/data/run_summary.json')),
    )

SETTINGS = load_settings()
