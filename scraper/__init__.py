"""Jobminer package public API."""
from importlib import metadata as _metadata

try:
    __version__ = _metadata.version("jobminer")
except Exception:  # fallback when not installed
    __version__ = "0.1.0"

from .jobminer.db import JobDB  # re-export
from .jobminer.models import JobPosting  # re-export

__all__ = ["__version__","JobDB","JobPosting"]
