from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

HIGHWAY_RADIUS_FT = 800.0
TRANSIT_RADIUS_MI = 0.5
PLAYGROUND_RADIUS_MI = 0.5
GROCERY_RADIUS_MI = 0.5
SHELTER_RADIUS_MI = 0.25
STALE_MAX_AGE_DAYS = 30.0

SIGNAL_ORDER = ("highway", "transit", "playground", "grocery", "shelter")
ICON_BY_KEY = {
    "highway": "directions_car",
    "transit": "train",
    "playground": "park",
    "grocery": "local_grocery_store",
    "shelter": "health_and_safety",
}
RISK_KEYS = frozenset({"highway", "shelter"})


def ft_to_miles(ft: float) -> float:
    return float(ft) / 5280.0


def miles_to_ft(mi: float) -> float:
    return float(mi) * 5280.0


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in miles."""
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def parse_signals_json(raw: str | None) -> dict[str, dict[str, Any]]:
    if not raw or not str(raw).strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, val in data.items():
        if isinstance(val, dict):
            out[str(key)] = val
    return out


def hits_in_order(payload: dict[str, dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    hits: list[tuple[str, dict[str, Any]]] = []
    for key in SIGNAL_ORDER:
        entry = payload.get(key) or {}
        if entry.get("hit"):
            hits.append((key, entry))
    return hits


def tooltip_for(key: str, entry: dict[str, Any]) -> str:
    name = str(entry.get("name") or "Nearby").strip() or "Nearby"
    if key == "highway":
        dist = entry.get("distance_ft")
        if dist is None:
            return name
        return f"{int(round(float(dist)))} ft · {name}"
    dist = entry.get("distance_mi")
    if dist is None:
        return name
    return f"{float(dist):.2f} mi · {name}"


def is_stale(
    nearby_signals_at: str | None,
    *,
    now: datetime | None = None,
    max_age_days: float = STALE_MAX_AGE_DAYS,
) -> bool:
    if not nearby_signals_at or not str(nearby_signals_at).strip():
        return True
    now = now or datetime.now(timezone.utc)
    try:
        ts = datetime.fromisoformat(str(nearby_signals_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_days = (now - ts).total_seconds() / 86400.0
    return age_days > max_age_days
