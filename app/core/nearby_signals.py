from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, TypedDict

import requests

from app.core import overlay_cache

if TYPE_CHECKING:
    from app.core.models import Property

HIGHWAY_RADIUS_FT = 800.0
TRANSIT_RADIUS_MI = 0.5
PLAYGROUND_RADIUS_MI = 0.5
GROCERY_RADIUS_MI = 0.5
SHELTER_RADIUS_MI = 0.25
STALE_MAX_AGE_DAYS = 30.0

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
PLACES_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
CACHE_NAMESPACE = "nearby"
RAW_CACHE_MAX_AGE_S = 7 * 24 * 3600
REQUEST_TIMEOUT_S = 45
OVERPASS_USER_AGENT = "Homebuy/0.1 (local research app)"
OVERPASS_HEADERS = {
    "User-Agent": OVERPASS_USER_AGENT,
    "Accept": "application/json",
}

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

        locations: list[dict[str, Any]] = []
        if key == "highway" and element.get("type") == "way":
            geometry = element.get("geometry")
            if isinstance(geometry, list):
                locations = [point for point in geometry if isinstance(point, dict)]
        if not locations:
            location = element if element.get("type") == "node" else element.get("center")
            if isinstance(location, dict):
                locations = [location]

        nearest_location: tuple[float, float, float] | None = None
        for location in locations:
            try:
                candidate_lat = float(location["lat"])
                candidate_lng = float(location["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            candidate_distance = haversine_miles(
                pin_lat, pin_lng, candidate_lat, candidate_lng
            )
            if nearest_location is None or candidate_distance < nearest_location[2]:
                nearest_location = (
                    candidate_lat,
                    candidate_lng,
                    candidate_distance,
                )
        if nearest_location is None:
            continue
        lat, lng, distance_mi = nearest_location
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
    return f"[out:json][timeout:45];\n(\n  {body}\n);\nout geom tags;"


def _raw_cache_key(lat: float, lng: float) -> str:
    return f"overpass_{float(lat):.5f}_{float(lng):.5f}"


def _places_raw_cache_key(
    lat: float,
    lng: float,
    *,
    radius_m: int,
    place_type: str,
    keyword: str | None,
) -> str:
    readable = (
        f"{float(lat):.5f}_{float(lng):.5f}_{int(radius_m)}_{place_type or 'any'}"
    )
    digest = overlay_cache.cache_key(readable, keyword or "")
    return f"places_{readable}_{digest}"


def fetch_overpass(
    lat: float,
    lng: float,
    *,
    session: Any | None = None,
) -> dict:
    key = _raw_cache_key(lat, lng)
    cached = overlay_cache.read_json(
        CACHE_NAMESPACE, key, max_age_s=RAW_CACHE_MAX_AGE_S
    )
    if isinstance(cached, dict):
        return cached

    client = session or requests
    query = build_overpass_query(lat, lng)
    # Overpass public mirrors rate-limit aggressively; rotate on 406/429/5xx.
    last_error: Exception | None = None
    for url in OVERPASS_URLS:
        try:
            response = client.post(
                url,
                data={"data": query},
                headers=OVERPASS_HEADERS,
                timeout=REQUEST_TIMEOUT_S,
            )
            if response.status_code in {406, 429, 502, 503, 504}:
                last_error = requests.HTTPError(
                    f"{response.status_code} for url: {url}",
                    response=response,
                )
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Overpass returned an invalid response")
            overlay_cache.write_json(CACHE_NAMESPACE, key, payload)
            return payload
        except (requests.RequestException, ValueError, TypeError) as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    raise RuntimeError("Overpass request failed")


def fetch_places_nearby(
    lat: float,
    lng: float,
    *,
    api_key: str,
    place_type: str,
    keyword: str | None,
    radius_m: int,
    session: Any | None = None,
) -> list[dict]:
    cache_key = _places_raw_cache_key(
        lat,
        lng,
        radius_m=radius_m,
        place_type=place_type,
        keyword=keyword,
    )
    cached = overlay_cache.read_json(
        CACHE_NAMESPACE, cache_key, max_age_s=RAW_CACHE_MAX_AGE_S
    )
    if isinstance(cached, dict):
        payload = cached
    else:
        params: dict[str, Any] = {
            "location": f"{lat},{lng}",
            "radius": int(radius_m),
            "key": api_key,
        }
        if place_type:
            params["type"] = place_type
        if keyword:
            params["keyword"] = keyword
        client = session or requests
        response = client.get(
            PLACES_NEARBY_URL,
            params=params,
            timeout=REQUEST_TIMEOUT_S,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            overlay_cache.write_json(CACHE_NAMESPACE, cache_key, payload)
    if not isinstance(payload, dict):
        raise ValueError("Places returned an invalid response")
    status = str(payload.get("status") or "")
    if status not in {"OK", "ZERO_RESULTS"}:
        message = str(payload.get("error_message") or status or "unknown error")
        raise ValueError(f"Places request failed: {message}")
    results = payload.get("results")
    return [result for result in results or [] if isinstance(result, dict)]


def parse_places_results(
    results: list[dict],
    *,
    pin_lat: float,
    pin_lng: float,
    radius_mi: float,
) -> list[NearestHit]:
    hits: list[NearestHit] = []
    for result in results:
        types = {
            str(value)
            for value in result.get("types", [])
            if isinstance(value, str)
        }
        if "convenience_store" in types and not (
            {"supermarket", "grocery_or_supermarket"} & types
        ):
            continue
        try:
            location = result["geometry"]["location"]
            lat = float(location["lat"])
            lng = float(location["lng"])
        except (KeyError, TypeError, ValueError):
            continue
        distance_mi = haversine_miles(pin_lat, pin_lng, lat, lng)
        if distance_mi > radius_mi:
            continue
        name = str(result.get("name") or "Nearby place").strip() or "Nearby place"
        hits.append(
            {
                "name": name,
                "lat": lat,
                "lng": lng,
                "distance_mi": distance_mi,
            }
        )
    return sorted(hits, key=lambda hit: hit["distance_mi"])


def google_key() -> str:
    return (os.getenv("GOOGLE_MAPS_API_KEY") or "").strip()


def _error_message(exc: Exception) -> str:
    return str(exc).strip() or exc.__class__.__name__


def compute_signals(
    lat: float,
    lng: float,
    *,
    api_key: str | None = None,
) -> dict[str, dict]:
    try:
        overpass = fetch_overpass(lat, lng)
        elements = overpass.get("elements", [])
        if not isinstance(elements, list):
            elements = []
        osm_hits = classify_overpass_nearest(elements, pin_lat=lat, pin_lng=lng)
        overpass_error: str | None = None
    except Exception as exc:
        osm_hits = {key: None for key in SIGNAL_ORDER}
        overpass_error = _error_message(exc)

    payload = {
        key: signal_entry_from_hit(key, osm_hits[key], error=overpass_error)
        for key in SIGNAL_ORDER
    }
    key = google_key() if api_key is None else api_key.strip()
    if not key:
        return payload

    places_specs = {
        "grocery": [("supermarket", None, math.ceil(GROCERY_RADIUS_MI * 1609.344))],
        "shelter": [
            (
                "establishment",
                "homeless shelter",
                math.ceil(SHELTER_RADIUS_MI * 1609.344),
            ),
            (
                "establishment",
                "drug rehabilitation|transitional housing",
                math.ceil(SHELTER_RADIUS_MI * 1609.344),
            ),
        ],
    }
    for signal_key, searches in places_specs.items():
        try:
            results: list[dict] = []
            for place_type, keyword, radius_m in searches:
                results.extend(
                    fetch_places_nearby(
                        lat,
                        lng,
                        api_key=key,
                        place_type=place_type,
                        keyword=keyword,
                        radius_m=radius_m,
                    )
                )
            hits = parse_places_results(
                results,
                pin_lat=lat,
                pin_lng=lng,
                radius_mi=_signal_radius_mi(signal_key),
            )
            payload[signal_key] = signal_entry_from_hit(
                signal_key, nearest_within(hits, _signal_radius_mi(signal_key))
            )
        except Exception as exc:
            payload[signal_key] = signal_entry_from_hit(
                signal_key,
                osm_hits[signal_key],
                error=None if osm_hits[signal_key] is not None else _error_message(exc),
            )
    return payload


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


def refresh_property_signals(prop: Property) -> dict[str, Any]:
    """Compute and cache nearby signals on a property without committing."""
    if prop.latitude is None or prop.longitude is None:
        return parse_signals_json(prop.nearby_signals)
    try:
        payload = compute_signals(float(prop.latitude), float(prop.longitude))
    except Exception as exc:  # noqa: BLE001 - never break add-home
        payload = {
            key: {"hit": False, "error": _error_message(exc)}
            for key in SIGNAL_ORDER
        }
    prop.nearby_signals = json.dumps(payload)
    prop.nearby_signals_at = datetime.now(timezone.utc).isoformat()
    return payload


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


def needs_refresh(
    nearby_signals_at: str | None,
    nearby_signals: str | None = None,
    *,
    now: datetime | None = None,
    max_age_days: float = STALE_MAX_AGE_DAYS,
) -> bool:
    """True when cache is missing, aged out, or only stores fetch errors."""
    if is_stale(nearby_signals_at, now=now, max_age_days=max_age_days):
        return True
    payload = parse_signals_json(nearby_signals)
    if not payload:
        return True
    if any(bool(entry.get("hit")) for entry in payload.values()):
        return False
    # Failed Overpass/Places runs were previously stuck for 30d with hit:false+error.
    return any(bool(entry.get("error")) for entry in payload.values())
