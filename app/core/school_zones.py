"""Assigned school zones via district attendance GIS (LAUSD first)."""

from __future__ import annotations

from typing import Any

import requests

from app.core.geo import haversine_miles
from app.core.overlay_cache import cache_key, read_json, write_json

REQUEST_TIMEOUT_S = 30
CACHE_MAX_AGE_S = 7 * 24 * 3600
CACHE_NS = "school_zones"
CACHE_REV = "v1"

LAUSD_BASE = (
    "https://maps.lacity.org/lahub/rest/services/LAUSD_Schools/MapServer"
)
# level -> (attendance_layer_id, map_type filter for school points)
LAUSD_LEVELS: dict[str, tuple[int, str]] = {
    "elementary": (4, "ES"),
    "middle": (5, "MS"),
    "high": (6, "HS"),
}

# Rough LAUSD district extent (min_lat, max_lat, min_lng, max_lng) used only
# to distinguish "outside the district" from "inside but boundary gap" when
# none of the three attendance layers return a hit.
LAUSD_BBOX: tuple[float, float, float, float] = (33.70, 34.35, -118.70, -118.15)

# Candidate attribute keys carrying an attendance polygon's unique id,
# checked in order (varies slightly by layer/level).
_ATTENDANCE_KEY_FIELDS: tuple[str, ...] = (
    "KEY_",
    "ES_KEY",
    "MS_KEY",
    "HS_KEY",
    "OBJECTID",
)


def point_in_ring(lng: float, lat: float, ring: list[list[float]]) -> bool:
    """Ray-cast; ring vertices are [lng, lat]."""
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = float(ring[i][0]), float(ring[i][1])
        xj, yj = float(ring[j][0]), float(ring[j][1])
        if ((yi > lat) != (yj > lat)) and (
            lng < (xj - xi) * (lat - yi) / (yj - yi + 0.0) + xi
        ):
            inside = not inside
        j = i
    return inside


def point_in_polygon(
    lng: float, lat: float, rings: list[list[list[float]]]
) -> bool:
    if not rings:
        return False
    if not point_in_ring(lng, lat, rings[0]):
        return False
    for hole in rings[1:]:
        if point_in_ring(lng, lat, hole):
            return False
    return True


def pick_school_in_zone(
    pin_lng: float,
    pin_lat: float,
    rings: list[list[list[float]]],
    candidates: list[dict[str, Any]],
    *,
    map_type: str,
) -> dict[str, Any] | None:
    """Pick the best school-point candidate whose location falls inside ``rings``.

    Prefers an exact ``map_type`` match; when several candidates remain,
    picks the one closest to the pin (haversine).
    """
    inside = [
        c
        for c in candidates
        if point_in_polygon(float(c["lng"]), float(c["lat"]), rings)
    ]
    if not inside:
        return None
    exact = [c for c in inside if c.get("map_type") == map_type]
    pool = exact if exact else inside
    if len(pool) == 1:
        return pool[0]
    return min(
        pool,
        key=lambda c: haversine_miles(
            pin_lat, pin_lng, float(c["lat"]), float(c["lng"])
        ),
    )


def schools_from_attendance_payloads(
    pin_lat: float,
    pin_lng: float,
    attendance: dict[str, dict[str, Any] | None],
    school_candidates: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any] | None]:
    """Pure assembly: attendance rings + school-point candidates -> AssignedSchool per level."""
    result: dict[str, dict[str, Any] | None] = {}
    for level, (_, map_type) in LAUSD_LEVELS.items():
        zone = attendance.get(level)
        if not zone:
            result[level] = None
            continue
        rings = zone.get("rings") or []
        candidates = school_candidates.get(level) or []
        picked = pick_school_in_zone(
            pin_lng, pin_lat, rings, candidates, map_type=map_type
        )
        if picked is None:
            result[level] = None
            continue
        result[level] = {
            "level": level,
            "name": picked.get("name") or "School",
            "city": picked.get("city") or "",
            "state": "CA",
            "cds_code": picked.get("cds_code") or "",
            "map_type": picked.get("map_type") or map_type,
            "attendance_key": zone.get("key"),
            "source": "LAUSD",
        }
    return result


def _query_lausd_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    """Thin GET + JSON wrapper for LAUSD ArcGIS REST endpoints."""
    resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_S)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict):
        raise ValueError("Unexpected LAUSD response")
    if payload.get("error"):
        raise ValueError(str(payload["error"]))
    return payload


def _fetch_attendance(level: str, lat: float, lng: float) -> dict[str, Any] | None:
    """Query the level's attendance-boundary layer for the point; first hit wins."""
    layer_id, _map_type = LAUSD_LEVELS[level]
    url = f"{LAUSD_BASE}/{layer_id}/query"
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
    }
    payload = _query_lausd_json(url, params)
    features = payload.get("features") or []
    if not features:
        return None
    feat = features[0]
    rings = (feat.get("geometry") or {}).get("rings")
    attrs = feat.get("attributes") or {}
    key: Any = None
    for field in _ATTENDANCE_KEY_FIELDS:
        if attrs.get(field) is not None:
            key = attrs.get(field)
            break
    return {"rings": rings, "key": key}


def _fetch_school_candidates(
    map_type: str, lat: float, lng: float
) -> list[dict[str, Any]]:
    """Query school points (layer 0) within 3 mi of the pin for a given MAP_TYPE."""
    url = f"{LAUSD_BASE}/0/query"
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "distance": 3,
        "units": "esriSRUnit_StatuteMile",
        "spatialRel": "esriSpatialRelIntersects",
        "where": f"MAP_TYPE='{map_type}'",
        "outFields": "FULLNAME,MPD_NAME,CDSCODE,CITY,MAP_TYPE,ADDRESS",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
    }
    payload = _query_lausd_json(url, params)
    features = payload.get("features") or []
    candidates: list[dict[str, Any]] = []
    for feat in features:
        attrs = feat.get("attributes") or {}
        geom = feat.get("geometry") or {}
        lng_c, lat_c = geom.get("x"), geom.get("y")
        if lng_c is None or lat_c is None:
            continue
        try:
            lng_c, lat_c = float(lng_c), float(lat_c)
        except (TypeError, ValueError):
            continue
        candidates.append(
            {
                "name": attrs.get("FULLNAME") or attrs.get("MPD_NAME") or "School",
                "lng": lng_c,
                "lat": lat_c,
                "map_type": attrs.get("MAP_TYPE"),
                "city": attrs.get("CITY") or "",
                "cds_code": str(attrs.get("CDSCODE") or ""),
            }
        )
    return candidates


def _empty_schools() -> dict[str, None]:
    return {level: None for level in LAUSD_LEVELS}


def resolve_assigned(lat: float | None, lng: float | None) -> dict[str, Any]:
    """Resolve assigned elementary/middle/high schools from LAUSD attendance GIS."""
    if lat is None or lng is None:
        return {
            "status": "no_pin",
            "source": None,
            "message": "No coordinates for this property yet.",
            "schools": _empty_schools(),
        }

    key = cache_key(CACHE_REV, f"{round(lat, 5)}", f"{round(lng, 5)}")
    cached = read_json(CACHE_NS, key, max_age_s=CACHE_MAX_AGE_S)
    if isinstance(cached, dict):
        return cached

    try:
        attendance: dict[str, dict[str, Any] | None] = {}
        school_candidates: dict[str, list[dict[str, Any]]] = {}
        for level, (_, map_type) in LAUSD_LEVELS.items():
            zone = _fetch_attendance(level, lat, lng)
            attendance[level] = zone
            school_candidates[level] = (
                _fetch_school_candidates(map_type, lat, lng) if zone else []
            )
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "source": None,
            "message": f"LAUSD lookup failed: {exc}",
            "schools": _empty_schools(),
        }

    schools = schools_from_attendance_payloads(lat, lng, attendance, school_candidates)

    if any(schools.values()):
        result = {
            "status": "ok",
            "source": "LAUSD attendance",
            "message": "Assigned schools resolved from LAUSD attendance boundaries.",
            "schools": schools,
        }
    else:
        min_lat, max_lat, min_lng, max_lng = LAUSD_BBOX
        in_bbox = min_lat <= lat <= max_lat and min_lng <= lng <= max_lng
        if in_bbox:
            result = {
                "status": "gap",
                "source": "LAUSD attendance",
                "message": (
                    "Inside the LAUSD area but no attendance boundary "
                    "matched this point (rare boundary gap)."
                ),
                "schools": schools,
            }
        else:
            result = {
                "status": "outside",
                "source": None,
                "message": "Outside LAUSD attendance boundaries.",
                "schools": schools,
            }

    write_json(CACHE_NS, key, result)
    return result
