"""In-process TTL memo cache."""

from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_store: dict[tuple[str, str], tuple[float, Any]] = {}


def memo_get(ns: str, key: str) -> Any | None:
    with _lock:
        entry = _store.get((ns, key))
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del _store[(ns, key)]
            return None
        return value


def memo_set(ns: str, key: str, value: Any, *, ttl_s: float) -> None:
    with _lock:
        _store[(ns, key)] = (time.time() + ttl_s, value)


def memo_clear(ns: str | None = None) -> None:
    with _lock:
        if ns is None:
            _store.clear()
        else:
            to_remove = [k for k in _store if k[0] == ns]
            for k in to_remove:
                del _store[k]
