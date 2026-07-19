"""Disk cache for map overlay API responses under data/cache/."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from app.core.paths import DATA_DIR


def _cache_root() -> Path:
    return DATA_DIR / "cache"


def cache_dir(*parts: str) -> Path:
    path = _cache_root().joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_key(*parts: str) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def read_json(namespace: str, key: str, *, max_age_s: float | None = None) -> Any | None:
    path = cache_dir(namespace) / f"{key}.json"
    if not path.is_file():
        return None
    if max_age_s is not None:
        age = time.time() - path.stat().st_mtime
        if age > max_age_s:
            path.unlink(missing_ok=True)
            return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(namespace: str, key: str, payload: Any) -> Path:
    path = cache_dir(namespace) / f"{key}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
