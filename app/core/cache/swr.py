"""Stale-while-revalidate disk cache helper."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from app.core.cache.disk import _resolve_path, read_json, write_json


def swr_get(
    ns: str,
    key: str,
    *,
    max_age_s: float,
    soft_age_s: float,
    factory: Callable[[], Any],
) -> Any | None:
    path, _ = _resolve_path(ns, key)
    if path is None:
        fresh = factory()
        if fresh is not None:
            write_json(ns, key, fresh)
        return fresh

    age = time.time() - path.stat().st_mtime
    if age > max_age_s:
        path.unlink(missing_ok=True)
        fresh = factory()
        if fresh is not None:
            write_json(ns, key, fresh)
        return fresh

    payload = read_json(ns, key)
    if payload is None:
        fresh = factory()
        if fresh is not None:
            write_json(ns, key, fresh)
        return fresh

    # Fresh (age <= soft_age_s) or soft-stale (soft_age_s < age <= max_age_s):
    # return cached payload; caller may refresh in the background.
    return payload
