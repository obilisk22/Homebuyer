"""Nearby public schools from NCES (no GreatSchools / no API key).

Approach
--------
Query NCES ArcGIS REST public-school point layers by a WGS84 envelope
around the property pin (default ~4 miles). This avoids a national
shapefile download; CA pins work the same as any CONUS pin.

Primary service (CCD school points, includes school level)::

    https://nces.ed.gov/arcgis/rest/services/CCD/CCD_Data/MapServer/4

Fallbacks: LocaleViewer PublicSchools24_25, then legacy EDGE opengis
layers (often offline). Attendance-boundary polygons are out of scope
for v1.
"""

from __future__ import annotations

import math
from typing import Any

import requests

from app.core.geo import haversine_miles
from app.core.overlay_cache import cache_key, read_json, write_json

REQUEST_TIMEOUT_S = 45
CACHE_MAX_AGE_S = 7 * 24 * 3600
DEFAULT_RADIUS_MI = 4.0
MAX_SCHOOLS = 80
LIST_LIMIT = 8

# Miles per degree latitude (approx); longitude scaled by cos(lat).
_MI_PER_DEG_LAT = 69.0

# CCD has SLEVEL_TEXT; LocaleViewer / EDGE use NAME+LEVEL (when online).
NCES_QUERY_ENDPOINTS: tuple[dict[str, str], ...] = (
    {
        "url": (
            "https://nces.ed.gov/arcgis/rest/services/CCD/CCD_Data/"
            "MapServer/4/query"
        ),
        "out_fields": (
            "SCH_NAME,NCESSCH,LEAID,ST_LEAID,LATCOD,LONCOD,SLEVEL_TEXT,"
            "NMCNTY,CNTY,LSTATE,LSTREET1,LCITY,LZIP,SURVYEAR"
        ),
    },
    {
        "url": (
            "https://nces.ed.gov/arcgis/rest/services/Locale/LocaleViewer/"
            "MapServer/2/query"
        ),
        "out_fields": (
            "NAME,NCESSCH,LEAID,LAT,LON,NMCNTY,CNTY,STATE,"
            "STREET,CITY,ZIP,SCHOOLYEAR"
        ),
    },
    {
        "url": (
            "https://nces.ed.gov/opengis/rest/services/K12_School_Locations/"
            "EDGE_GEOCODE_PUBLICSCH_2425/MapServer/0/query"
        ),
        "out_fields": (
            "NAME,NCESSCH,LEAID,LAT,LON,LEVEL,ST_LEAID,NMCNTY,CNTY,STATE,"
            "STREET,CITY,ZIP,SCHOOLYEAR"
        ),
    },
    {
        "url": (
            "https://nces.ed.gov/opengis/rest/services/K12_School_Locations/"
            "EDGE_GEOCODE_PUBLICSCH_2324/MapServer/0/query"
        ),
        "out_fields": (
            "NAME,NCESSCH,LEAID,LAT,LON,LEVEL,ST_LEAID,NMCNTY,CNTY,STATE,"
            "STREET,CITY,ZIP,SCHOOLYEAR"
        ),
    },
)

# Primary endpoint URL (used when recording source on cached payloads).
NCES_QUERY_URL = NCES_QUERY_ENDPOINTS[0]["url"]

LEVEL_COLORS: dict[str, str] = {
    "Elementary": "#00E5FF",
    "Middle": "#B8FF3C",
    "High": "#FF2BD6",
    "Other": "#FFC107",
}

SCHOOLS_LEGEND: list[tuple[str, str]] = [
    ("Elementary", "#00E5FF"),
    ("Middle", "#B8FF3C"),
    ("High", "#FF2BD6"),
    ("Other", "#FFC107"),
]


def miles_to_half_span_deg(radius_mi: float, lat: float) -> float:
    """Convert search radius (miles) to a half-span envelope in degrees."""
    lat_span = radius_mi / _MI_PER_DEG_LAT
    cos_lat = max(0.2, abs(math.cos(math.radians(lat))))
    lng_span = radius_mi / (_MI_PER_DEG_LAT * cos_lat)
    return max(lat_span, lng_span)


def normalize_level(raw: object) -> str:
    """Map NCES LEVEL codes / strings to Elementary / Middle / High / Other."""
    if raw is None:
        return "Other"
    if isinstance(raw, (int, float)):
        code = int(raw)
        return {1: "Elementary", 2: "Middle", 3: "High", 4: "Other"}.get(code, "Other")
    text = str(raw).strip().lower()
    if not text:
        return "Other"
    if text in {"1", "elementary", "elem", "primary"}:
        return "Elementary"
    if text in {"2", "middle", "junior", "junior high", "jr high"}:
        return "Middle"
    if text in {"3", "high", "senior", "secondary"}:
        return "High"
    if "elem" in text or "primary" in text:
        return "Elementary"
    if "middle" in text or "junior" in text:
        return "Middle"
    if "high" in text or "senior" in text:
        return "High"
    return "Other"


def nces_school_url(ncessch: str) -> str:
    ncessch = (ncessch or "").strip()
    if not ncessch:
        return "https://nces.ed.gov/ccd/schoolsearch/"
    return (
        "https://nces.ed.gov/ccd/schoolsearch/school_detail.asp?Search=1&ID="
        f"{ncessch}"
    )


def _attrs_from_feature(feat: dict[str, Any]) -> dict[str, Any]:
    if "attributes" in feat:
        raw = dict(feat.get("attributes") or {})
    else:
        raw = dict(feat.get("properties") or {})
    # Normalize CCD vs EDGE / LocaleViewer field names.
    if not raw.get("NAME") and raw.get("SCH_NAME"):
        raw["NAME"] = raw["SCH_NAME"]
    if raw.get("LAT") is None and raw.get("LATCOD") is not None:
        raw["LAT"] = raw["LATCOD"]
    if raw.get("LON") is None and raw.get("LONCOD") is not None:
        raw["LON"] = raw["LONCOD"]
    if raw.get("LEVEL") is None and raw.get("SLEVEL_TEXT") is not None:
        raw["LEVEL"] = raw["SLEVEL_TEXT"]
    if not raw.get("STREET") and raw.get("LSTREET1"):
        raw["STREET"] = raw["LSTREET1"]
    if not raw.get("CITY") and raw.get("LCITY"):
        raw["CITY"] = raw["LCITY"]
    if not raw.get("STATE") and (raw.get("LSTATE") or raw.get("STABR")):
        raw["STATE"] = raw.get("LSTATE") or raw.get("STABR")
    if not raw.get("ZIP") and raw.get("LZIP"):
        raw["ZIP"] = raw["LZIP"]
    return raw


def _coords_from_feature(feat: dict[str, Any], attrs: dict[str, Any]) -> tuple[float, float] | None:
    geom = feat.get("geometry") or {}
    if "y" in geom and "x" in geom:
        try:
            return float(geom["y"]), float(geom["x"])
        except (TypeError, ValueError):
            pass
    coords = (geom.get("coordinates") if isinstance(geom, dict) else None) or None
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        try:
            return float(coords[1]), float(coords[0])
        except (TypeError, ValueError):
            pass
    try:
        lat = float(attrs.get("LAT"))
        lng = float(attrs.get("LON") or attrs.get("LONG") or attrs.get("LNG"))
        if math.isfinite(lat) and math.isfinite(lng):
            return lat, lng
    except (TypeError, ValueError):
        pass
    return None


def parse_nces_features(
    payload: dict[str, Any],
    *,
    pin_lat: float,
    pin_lng: float,
    radius_mi: float,
) -> list[dict[str, Any]]:
    """Normalize EDGE JSON/GeoJSON features → school dicts within radius."""
    features = payload.get("features") or []
    out: list[dict[str, Any]] = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        attrs = _attrs_from_feature(feat)
        coords = _coords_from_feature(feat, attrs)
        if coords is None:
            continue
        lat, lng = coords
        dist = haversine_miles(pin_lat, pin_lng, lat, lng)
        if dist > radius_mi + 0.05:
            continue
        name = str(attrs.get("NAME") or "School").strip() or "School"
        ncessch = str(attrs.get("NCESSCH") or "").strip()
        level = normalize_level(attrs.get("LEVEL"))
        district = str(
            attrs.get("ST_LEAID") or attrs.get("LEAID") or attrs.get("NMCNTY") or ""
        ).strip()
        out.append(
            {
                "name": name,
                "level": level,
                "lat": lat,
                "lng": lng,
                "distance_mi": round(dist, 2),
                "ncessch": ncessch,
                "district": district,
                "city": str(attrs.get("CITY") or "").strip(),
                "url": nces_school_url(ncessch),
                "fillColor": LEVEL_COLORS.get(level, LEVEL_COLORS["Other"]),
            }
        )
    out.sort(key=lambda s: (s["distance_mi"], s["name"]))
    return out[:MAX_SCHOOLS]


def _query_envelope(
    url: str,
    bbox: tuple[float, float, float, float],
    *,
    out_fields: str,
) -> dict[str, Any]:
    min_lng, min_lat, max_lng, max_lat = bbox
    resp = requests.get(
        url,
        params={
            "where": "1=1",
            "geometry": f"{min_lng},{min_lat},{max_lng},{max_lat}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": out_fields,
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
            "resultRecordCount": MAX_SCHOOLS,
        },
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict):
        raise ValueError("Unexpected NCES response")
    if payload.get("error"):
        raise ValueError(str(payload["error"]))
    return payload


def fetch_schools_near_pin(
    lat: float,
    lng: float,
    *,
    radius_mi: float = DEFAULT_RADIUS_MI,
) -> dict[str, Any]:
    """Return ``{schools, meta}`` for schools within ``radius_mi`` of the pin."""
    half = miles_to_half_span_deg(radius_mi, lat)
    bbox = (lng - half, lat - half, lng + half, lat + half)
    key = cache_key(
        "nces",
        f"{lat:.4f}",
        f"{lng:.4f}",
        f"{radius_mi:.1f}",
    )
    cached = read_json("schools_nces", key, max_age_s=CACHE_MAX_AGE_S)
    if isinstance(cached, dict) and isinstance(cached.get("schools"), list):
        return cached

    last_err: Exception | None = None
    payload: dict[str, Any] | None = None
    source_url = NCES_QUERY_URL
    for endpoint in NCES_QUERY_ENDPOINTS:
        url = endpoint["url"]
        try:
            payload = _query_envelope(url, bbox, out_fields=endpoint["out_fields"])
            source_url = url
            break
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
    if payload is None:
        raise RuntimeError(
            f"NCES school service unavailable: {last_err}"
        ) from last_err

    schools = parse_nces_features(
        payload, pin_lat=lat, pin_lng=lng, radius_mi=radius_mi
    )
    result = {
        "schools": schools,
        "meta": {
            "radius_mi": radius_mi,
            "count": len(schools),
            "source": "NCES public school locations",
            "message": (
                f"{len(schools)} public schools within {radius_mi:g} mi"
                if schools
                else f"No NCES public schools within {radius_mi:g} mi"
            ),
            "query_url": source_url,
        },
    }
    write_json("schools_nces", key, result)
    return result


def schools_to_geojson(schools: list[dict[str, Any]]) -> dict[str, Any]:
    """Point FeatureCollection for Map markers (popup + fillColor)."""
    features: list[dict[str, Any]] = []
    for s in schools:
        level = s.get("level") or "Other"
        dist = s.get("distance_mi")
        dist_txt = f"{dist:.1f} mi" if isinstance(dist, (int, float)) else ""
        district = s.get("district") or ""
        popup = (
            f"<b>{s.get('name') or 'School'}</b><br>"
            f"{level}"
            + (f" · {dist_txt}" if dist_txt else "")
            + (f"<br>LEA {district}" if district else "")
        )
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(s["lng"]), float(s["lat"])],
                },
                "properties": {
                    "name": s.get("name"),
                    "level": level,
                    "distance_mi": dist,
                    "fillColor": s.get("fillColor") or LEVEL_COLORS.get(level, "#FFC107"),
                    "popup": popup,
                    "url": s.get("url") or "",
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {"count": len(features)},
    }


def nearest_schools_list(
    lat: float,
    lng: float,
    *,
    radius_mi: float = DEFAULT_RADIUS_MI,
    limit: int = LIST_LIMIT,
) -> dict[str, Any]:
    """Convenience for the Map / Neighborhood panel list."""
    result = fetch_schools_near_pin(lat, lng, radius_mi=radius_mi)
    schools = list(result.get("schools") or [])[:limit]
    meta = dict(result.get("meta") or {})
    meta["list_limit"] = limit
    return {"schools": schools, "meta": meta}
