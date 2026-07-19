from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any, TypedDict

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


class NearestHit(TypedDict):
    name: str
    lat: float
    lng: float
    distance_mi: float


def ft_to_miles(ft: float) -> float:
    return float(ft) / 5280.0


def miles_to_ft(mi: float) -> float:
    return float(mi) * 5280.0


def _signal_radius_mi(key: str) -> float:
    return {
        "highway": ft_to_miles(HIGHWAY_RADIUS_FT),
        "transit": TRANSIT_RADIUS_MI,
        "playground": PLAYGROUND_RADIUS_MI,
        "grocery": GROCERY_RADIUS_MI,
        "shelter": SHELTER_RADIUS_MI,
    }[key]


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in miles."""
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _signal_key(tags: dict[str, Any]) -> str | None:
    highway = tags.get("highway")
    railway = tags.get("railway")
    station = tags.get("station")
    if highway in {"motorway", "motorway_link"}:
        return "highway"
    if (
        (railway == "station" and station in {"subway", "light_rail"})
        or railway in {"subway_entrance", "tram_stop"}
        or (railway == "halt" and tags.get("light_rail") == "yes")
    ):
        return "transit"
    if tags.get("leisure") == "playground":
        return "playground"
    if tags.get("shop") in {"supermarket", "grocery"}:
        return "grocery"
    social_facility = tags.get("social_facility")
    if tags.get("amenity") == "social_facility" and (
        social_facility
        in {"shelter", "drug_rehabilitation", "transitional"}
        or tags.get("social_facility:for") == "homeless"
    ):
        return "shelter"
    if (
        tags.get("amenity") == "shelter"
        and tags.get("shelter_type") == "homeless"
    ):
        return "shelter"
    return None


def _fallback_name(key: str) -> str:
    return {
        "highway": "Freeway",
        "transit": "Rail stop",
        "playground": "Playground",
        "grocery": "Grocery",
        "shelter": "Shelter",
    }[key]


def parse_overpass_elements(
    elements: list[dict],
    *,
    pin_lat: float,
    pin_lng: float,
    radius_mi: float,
) -> list[NearestHit]:
    nearest_by_key = _classify_overpass_nearest(
        elements,
        pin_lat=pin_lat,
        pin_lng=pin_lng,
        outer_radius_mi=radius_mi,
    )
    return [nearest_by_key[key] for key in SIGNAL_ORDER if nearest_by_key[key] is not None]


def classify_overpass_nearest(
    elements: list[dict],
    *,
    pin_lat: float,
    pin_lng: float,
) -> dict[str, NearestHit | None]:
    """Return the nearest in-range Overpass hit for every signal key."""
    return _classify_overpass_nearest(
        elements,
        pin_lat=pin_lat,
        pin_lng=pin_lng,
        outer_radius_mi=None,
    )


def _classify_overpass_nearest(
    elements: list[dict],
    *,
    pin_lat: float,
    pin_lng: float,
    outer_radius_mi: float | None,
) -> dict[str, NearestHit | None]:
    nearest_by_key: dict[str, NearestHit | None] = {
        key: None for key in SIGNAL_ORDER
    }
    for element in elements:
        tags = element.get("tags")
        if not isinstance(tags, dict):
            continue
        key = _signal_key(tags)
        if key is None:
            continue

        location = element.get("center") if element.get("type") != "node" else element
        if not isinstance(location, dict):
            continue
        try:
            lat = float(location["lat"])
            lng = float(location["lon"])
        except (KeyError, TypeError, ValueError):
            continue

        distance_mi = haversine_miles(pin_lat, pin_lng, lat, lng)
        radius_mi = _signal_radius_mi(key)
        if outer_radius_mi is not None:
            radius_mi = min(radius_mi, outer_radius_mi)
        if distance_mi > radius_mi:
            continue
        name = str(tags.get("name") or tags.get("ref") or _fallback_name(key)).strip()
        hit: NearestHit = {
            "name": name or _fallback_name(key),
            "lat": lat,
            "lng": lng,
            "distance_mi": distance_mi,
        }
        current = nearest_by_key.get(key)
        if current is None or distance_mi < current["distance_mi"]:
            nearest_by_key[key] = hit
    return nearest_by_key


def nearest_within(
    hits: list[NearestHit], radius_mi: float
) -> NearestHit | None:
    candidates = [hit for hit in hits if hit["distance_mi"] <= radius_mi]
    return min(candidates, key=lambda hit: hit["distance_mi"], default=None)


def signal_entry_from_hit(
    key: str,
    hit: NearestHit | None,
    *,
    error: str | None = None,
) -> dict[str, Any]:
    if hit is None:
        entry: dict[str, Any] = {"hit": False}
        if error:
            entry["error"] = error
        return entry

    name = str(hit.get("name") or _fallback_name(key)).strip() or _fallback_name(key)
    if key == "highway":
        return {
            "hit": True,
            "distance_ft": miles_to_ft(hit["distance_mi"]),
            "name": name,
        }
    return {
        "hit": True,
        "distance_mi": round(hit["distance_mi"], 2),
        "name": name,
    }


def build_overpass_query(lat: float, lng: float) -> str:
    highway_around = f"(around:244,{lat},{lng})"
    nearby_around = f"(around:805,{lat},{lng})"
    clauses = [
        f'way["highway"="motorway"]{highway_around};',
        f'way["highway"="motorway_link"]{highway_around};',
        f'node["railway"="station"]["station"="subway"]{nearby_around};',
        f'way["railway"="station"]["station"="subway"]{nearby_around};',
        f'node["railway"="subway_entrance"]{nearby_around};',
        f'node["railway"="station"]["station"="light_rail"]{nearby_around};',
        f'way["railway"="station"]["station"="light_rail"]{nearby_around};',
        f'node["railway"="tram_stop"]{nearby_around};',
        f'node["railway"="halt"]["light_rail"="yes"]{nearby_around};',
        f'node["leisure"="playground"]{nearby_around};',
        f'way["leisure"="playground"]{nearby_around};',
        f'node["shop"="supermarket"]{nearby_around};',
        f'way["shop"="supermarket"]{nearby_around};',
        f'node["shop"="grocery"]{nearby_around};',
        f'way["shop"="grocery"]{nearby_around};',
    ]
    for element_type in ("node", "way"):
        for social_facility in ("shelter", "drug_rehabilitation", "transitional"):
            clauses.append(
                f'{element_type}["amenity"="social_facility"]'
                f'["social_facility"="{social_facility}"]{nearby_around};'
            )
        clauses.append(
            f'{element_type}["amenity"="social_facility"]'
            f'["social_facility:for"="homeless"]{nearby_around};'
        )
        clauses.append(
            f'{element_type}["amenity"="shelter"]'
            f'["shelter_type"="homeless"]{nearby_around};'
        )
    body = "\n  ".join(clauses)
    return f"[out:json][timeout:45];\n(\n  {body}\n);\nout center tags;"


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
