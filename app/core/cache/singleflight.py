"""Coalesce concurrent identical work into a single in-flight call."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

_lock = threading.Lock()
_inflight: dict[tuple[str, str], _Flight] = {}


class _Flight:
    __slots__ = ("event", "result", "error")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None


def singleflight(ns: str, key: str, factory: Callable[[], T]) -> T:
    flight_key = (ns, key)
    with _lock:
        existing = _inflight.get(flight_key)
        if existing is not None:
            flight = existing
            is_leader = False
        else:
            flight = _Flight()
            _inflight[flight_key] = flight
            is_leader = True

    if not is_leader:
        flight.event.wait()
        if flight.error is not None:
            raise flight.error
        return flight.result  # type: ignore[return-value]

    try:
        flight.result = factory()
    except BaseException as exc:
        flight.error = exc
        raise
    finally:
        with _lock:
            _inflight.pop(flight_key, None)
        flight.event.set()

    return flight.result  # type: ignore[return-value]
