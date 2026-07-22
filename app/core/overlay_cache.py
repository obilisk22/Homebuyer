"""Compatibility wrappers — prefer app.core.cache."""
from app.core.cache import cache_dir, cache_key, read_json, write_json

__all__ = ["cache_dir", "cache_key", "read_json", "write_json"]
