"""Disk cache under data/cache/."""

from __future__ import annotations

import gzip as gzip_mod
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

from app.core.paths import DATA_DIR

_log = logging.getLogger(__name__)


def cache_dir(*parts: str) -> Path:
    path = DATA_DIR / "cache"
    if parts:
        path = path.joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_key(*parts: str) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _resolve_path(namespace: str, key: str) -> tuple[Path | None, bool]:
    """Return (path, is_gzip) for an existing cache entry, or (None, False)."""
    base = cache_dir(namespace)
    gz_path = base / f"{key}.json.gz"
    if gz_path.is_file():
        return gz_path, True
    json_path = base / f"{key}.json"
    if json_path.is_file():
        return json_path, False
    return None, False


def read_json(namespace: str, key: str, *, max_age_s: float | None = None) -> Any | None:
    path, is_gzip = _resolve_path(namespace, key)
    if path is None:
        return None
    if max_age_s is not None:
        age = time.time() - path.stat().st_mtime
        if age > max_age_s:
            path.unlink(missing_ok=True)
            return None
    try:
        if is_gzip:
            with gzip_mod.open(path, "rt", encoding="utf-8") as fh:
                return json.load(fh)
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, gzip_mod.BadGzipFile):
        return None


def write_json(
    namespace: str,
    key: str,
    payload: Any,
    *,
    gzip: bool = False,
    max_bytes: int | None = None,
    refuse_oversize: bool = False,
) -> Path:
    data = json.dumps(payload).encode("utf-8")
    if max_bytes is not None and len(data) > max_bytes:
        _log.warning(
            "cache write exceeds max_bytes (%d > %d) for %s/%s",
            len(data),
            max_bytes,
            namespace,
            key,
        )
        if refuse_oversize:
            raise ValueError(f"payload exceeds max_bytes ({len(data)} > {max_bytes})")
    if gzip:
        path = cache_dir(namespace) / f"{key}.json.gz"
        with gzip_mod.open(path, "wt", encoding="utf-8") as fh:
            fh.write(data.decode("utf-8"))
    else:
        path = cache_dir(namespace) / f"{key}.json"
        path.write_bytes(data)
    return path


def prune_namespace(namespace: str, *, max_age_s: float) -> int:
    base = cache_dir(namespace)
    if not base.is_dir():
        return 0
    now = time.time()
    removed = 0
    for path in base.iterdir():
        if not path.is_file():
            continue
        if path.suffix not in (".json", ".gz"):
            continue
        age = now - path.stat().st_mtime
        if age > max_age_s:
            path.unlink(missing_ok=True)
            removed += 1
    return removed
