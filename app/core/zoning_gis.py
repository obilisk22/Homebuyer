"""Zoning near pin — City of LA (ZIMAS), Santa Monica (SCAG), LA County DRP.

Public ArcGIS REST only; no API key. Polygons are normalized to ACS-like
GeoJSON (fillColor + popup) for the Map tab.

City of LA uses ZIMAS MapServer layer **1102** (citywide Zoning). Layer 1101 is
Chapter 1A rollout only and must not be the sole source — it paints pockets.
Queries use an ACS-scale bbox and paginate past ArcGIS transfer limits.

Large FeatureCollections (~10–20 MB) need NiceGUI's Engine.IO
``max_http_buffer_size`` raised in ``app.main`` (default 1 MB drops the payload).
Do not over-simplify geometry (maxAllowableOffset / merge-by-zone) — that turns
parcels into triangle-like shapes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import requests

from app.core.crime_socrata import LA_COUNTY_BBOX, in_la_county, normalize_city
from app.core.overlay_cache import cache_key, read_json, write_json

REQUEST_TIMEOUT_S = 45
CACHE_MAX_AGE_S = 24 * 3600
# ~ACS-scale bbox (~2.5–3 mi half) so zoning fills the typical Map viewport, not a pin pocket.
DEFAULT_HALF_SPAN_DEG = 0.04
# When a dense city (e.g. Santa Monica) truncates at MAX_FEATURES, shrink toward the pin
# so ArcGIS returns parcels near the pin instead of the first N OBJECTIDs city-wide.
MIN_HALF_SPAN_DEG = 0.008  # ~0.55 mi
# Per-request page size (ZIMAS/DRP maxRecordCount is 2000); paginate until complete.
PAGE_SIZE = 1000
# Hard cap across pages so a huge bbox cannot stall the Map tab.
MAX_FEATURES = 5000
# Cache revision: binary-search max pin-local span under MAX_FEATURES.
CACHE_REV = "v6"

# City of LA — use MapServer **1102** (citywide Zoning), not **1101** (Chapter 1A).
# Root cause of pocket coverage: 1101 only has polygons where the new Chapter 1A code
# has rolled out (e.g. parts of Downtown). Westside / Hollywood / Venice often return
# 0 features on 1101 while 1102 fills the same bbox continuously. (Earlier note that
# 1102 returned empty was wrong for current WGS84 envelope queries.)
LA_CITY_QUERY_URL = (
    "https://zimas.lacity.org/arcgis/rest/services/zma/zimas/MapServer/1102/query"
)
# Unincorporated LA County
LA_COUNTY_QUERY_URL = (
    "https://arcgis.gis.lacounty.gov/arcgis/rest/services/DRP/Open_Data/MapServer/3/query"
)
# SCAG parcel zoning (WGS84) — used for Santa Monica + County incorporated fallback.
# City SM ArcGIS Online layer requires native State Plane; SCAG is reliable in 4326.
SCAG_LA_QUERY_URL = (
    "https://maps.scag.ca.gov/scaggis/rest/services/LDX/Zoning_poly_LA/MapServer/0/query"
)

# Rough Santa Monica city extent (WGS84). Keep the eastern edge west of Mar Vista /
# West LA (~-118.45) so empty-city pins there resolve to ZIMAS, not SM-only SCAG pockets.
SM_BBOX = (33.995, 34.055, -118.525, -118.460)  # min_lat, max_lat, min_lng, max_lng

ZONING_CATEGORY_COLORS: dict[str, str] = {
    "Residential": "#00E5FF",
    "Commercial": "#FF2BD6",
    "Industrial": "#FFC107",
    "Mixed / Other": "#B8FF3C",
    "Open / Public": "#8B96A8",
}

ZONING_LEGEND: list[tuple[str, str]] = [
    ("Residential", "#00E5FF"),
    ("Commercial", "#FF2BD6"),
    ("Industrial", "#FFC107"),
    ("Mixed / Other", "#B8FF3C"),
    ("Open / Public", "#8B96A8"),
]

@dataclass(frozen=True)
class ZoningFeed:
    id: str
    label: str
    query_url: str
    code_fields: tuple[str, ...]
    class_fields: tuple[str, ...]
    desc_fields: tuple[str, ...]
    out_fields: str
    where: str = "1=1"

FEEDS: dict[str, ZoningFeed] = {
    "la_city": ZoningFeed(
        id="la_city",
        label="City of Los Angeles (ZIMAS)",
        query_url=LA_CITY_QUERY_URL,
        code_fields=("ZONE_CMPLT",),
        class_fields=("ZONE_CLASS", "ZONELEGEND"),
        desc_fields=("ZONE_CLASS", "ZONELEGEND"),
        out_fields="ZONE_CMPLT,ZONE_CLASS,ZONELEGEND",
    ),
    "santa_monica": ZoningFeed(
        id="santa_monica",
        label="Santa Monica (SCAG zoning)",
        query_url=SCAG_LA_QUERY_URL,
        code_fields=("ZN24_CITY",),
        class_fields=("ZN24_SCAG", "CITY"),
        desc_fields=("CITY", "ZN24_SCAG"),
        out_fields="ZN24_CITY,ZN24_SCAG,CITY,APN24",
        where="CITY='Santa Monica'",
    ),
    "la_county": ZoningFeed(
        id="la_county",
        label="LA County unincorporated (DRP)",
        query_url=LA_COUNTY_QUERY_URL,
        code_fields=("ZONE", "Z_NAME"),
        class_fields=("Z_CATEGORY",),
        desc_fields=("Z_DESC", "Z_CATEGORY", "NAME"),
        out_fields="ZONE,Z_NAME,Z_DESC,Z_CATEGORY,NAME",
    ),
    "scag_la": ZoningFeed(
        id="scag_la",
        label="LA region (SCAG zoning)",
        query_url=SCAG_LA_QUERY_URL,
        code_fields=("ZN24_CITY",),
        class_fields=("CITY", "ZN24_SCAG"),
        desc_fields=("CITY", "ZN24_SCAG"),
        out_fields="ZN24_CITY,ZN24_SCAG,CITY,APN24",
    ),
}

def bbox_around(
    lat: float, lng: float, half_span_deg: float = DEFAULT_HALF_SPAN_DEG
) -> tuple[float, float, float, float]:
    """Return (min_lng, min_lat, max_lng, max_lat)."""
    return (
        lng - half_span_deg,
        lat - half_span_deg,
        lng + half_span_deg,
        lat + half_span_deg,
    )

def _in_sm_bbox(lat: float, lng: float) -> bool:
    min_lat, max_lat, min_lng, max_lng = SM_BBOX
    return min_lat <= lat <= max_lat and min_lng <= lng <= max_lng

def categorize_zone(code: str, class_or_desc: str = "") -> str:
    """Map zone code / class text → legend category."""
    blob = f"{code} {class_or_desc}".upper()
    # Strip bracket wrappers from new LA form-based codes for prefix checks.
    compact = re.sub(r"[\[\]\s\-_/]+", " ", blob)
    tokens = compact.split()

    if any(
        t in blob
        for t in (
            "OPEN SPACE",
            "PUBLIC FACILITY",
            "PUBLIC FAC",
            " PARK",
            "OS1",
            "PF-",
            " OS ",
        )
    ) or any(t.startswith("OS") or t.startswith("PF") for t in tokens):
        return "Open / Public"

    if any(
        t in blob
        for t in ("INDUSTRIAL", "MANUFACTURING", " PRODUCTION")
    ) or any(t.startswith("M") and not t.startswith("MU") for t in tokens if len(t) <= 4):
        # M / MR / CM — industrial-ish; CM often commercial manufacturing
        if any(t.startswith("CM") for t in tokens):
            return "Commercial"
        if any(re.match(r"^M\d", t) or t in {"M", "MR", "M1", "M2", "M3"} for t in tokens):
            return "Industrial"

    if any(
        t in blob for t in ("COMMERCIAL", "RETAIL", "BUSINESS")
    ) or any(
        t.startswith("C") and not t.startswith("CR") for t in tokens if len(t) <= 5
    ):
        # Prefer commercial over residential when C* present without R*
        if any(t.startswith("C") for t in tokens):
            return "Commercial"

    if any(
        t in blob
        for t in (
            "RESIDENTIAL",
            "SINGLE FAMILY",
            "MULTI-FAMILY",
            "MULTIFAMILY",
            "DWELLING",
        )
    ) or any(t.startswith("R") for t in tokens):
        return "Residential"

    # SM / SCAG short codes
    code_u = (code or "").upper().strip()
    if code_u.startswith(("R", "RA", "RS", "RD", "RM", "RH", "RW")):
        return "Residential"
    if code_u.startswith(("C", "BC", "NC", "GC", "OC", "NV")):
        # NV = Neighborhood Village (SM) → mixed/commercial-leaning
        if code_u.startswith("NV"):
            return "Mixed / Other"
        return "Commercial"
    if code_u.startswith(("M", "I")):
        return "Industrial"
    if code_u.startswith(("OS", "P", "PF", "A")):
        return "Open / Public"

    return "Mixed / Other"

def resolve_zoning_feed(
    city: str | None, lat: float | None = None, lng: float | None = None
) -> ZoningFeed | None:
    """Pick a zoning feed for the pin (SM → LA city → County / SCAG fallback later)."""
    name = normalize_city(city)
    if name in {"santa monica", "sm"}:
        return FEEDS["santa_monica"]
    # Explicit City of LA must win over the loose SM bbox (Mar Vista / Venice edge
    # pins sit inside SM_BBOX but are not Santa Monica — wrong feed → SM-only pockets).
    if name in {"los angeles", "la", "city of los angeles", "los angeles city"}:
        return FEEDS["la_city"]
    if lat is not None and lng is not None and _in_sm_bbox(float(lat), float(lng)):
        return FEEDS["santa_monica"]

    if in_la_county(city, lat, lng):
        # Prefer City of LA feed when city string is empty but pin is Westside LA city —
        # still try la_county first for unincorporated; build_zoning_geojson may fall back.
        if name and name not in {"los angeles", "la"} and "santa monica" not in name:
            return FEEDS["la_county"]
        # Empty city inside county: try LA city zoning first (common for scraped listings).
        if not name and lat is not None and lng is not None:
            return FEEDS["la_city"]
        return FEEDS["la_county"]

    return None

def zoning_supported(
    city: str | None, lat: float | None = None, lng: float | None = None
) -> bool:
    return resolve_zoning_feed(city, lat, lng) is not None

def _pick_field(props: dict[str, Any], names: tuple[str, ...]) -> str:
    for n in names:
        val = props.get(n)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""

def _headers() -> dict[str, str]:
    return {"User-Agent": "Homebuy/0.1 (local research app)"}

def _query_arcgis_geojson(
    feed: ZoningFeed,
    bbox: tuple[float, float, float, float],
) -> dict[str, Any]:
    """Query ArcGIS REST as GeoJSON, paginating past maxRecordCount / transfer limits.

    Without pagination, a typical LA bbox exceeds one page and the Map shows only a
    subset of parcels (visual “pockets”) even when the layer itself is contiguous.
    """
    min_lng, min_lat, max_lng, max_lat = bbox
    geometry = f"{min_lng},{min_lat},{max_lng},{max_lat}"
    features: list[Any] = []
    offset = 0
    truncated = False
    while True:
        page_size = min(PAGE_SIZE, MAX_FEATURES - len(features))
        if page_size <= 0:
            truncated = True
            break
        params = {
            "where": feed.where,
            "geometry": geometry,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": feed.out_fields,
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultRecordCount": str(page_size),
            "resultOffset": str(offset),
        }
        resp = requests.get(
            feed.query_url, params=params, headers=_headers(), timeout=REQUEST_TIMEOUT_S
        )
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict):
            raise ValueError(f"Unexpected zoning response from {feed.id}")
        if payload.get("error"):
            raise ValueError(str(payload["error"]))
        page = payload.get("features") or []
        if not isinstance(page, list):
            raise ValueError(f"Unexpected zoning features from {feed.id}")
        features.extend(page)
        exceeded = bool(payload.get("exceededTransferLimit"))
        if not exceeded or not page:
            break
        offset += len(page)
        if len(features) >= MAX_FEATURES:
            truncated = True
            break

    return {
        "type": "FeatureCollection",
        "features": features,
        "exceededTransferLimit": truncated,
    }

def normalize_zoning_feature(
    feat: dict[str, Any], feed: ZoningFeed
) -> dict[str, Any] | None:
    props_in = dict(feat.get("properties") or {})
    geom = feat.get("geometry")
    if not geom:
        return None
    code = _pick_field(props_in, feed.code_fields) or "—"
    class_txt = _pick_field(props_in, feed.class_fields)
    desc = _pick_field(props_in, feed.desc_fields) or class_txt
    category = categorize_zone(code, f"{class_txt} {desc}")
    color = ZONING_CATEGORY_COLORS.get(category, "#8B96A8")
    lines = [code]
    if desc and desc != code:
        lines.append(desc)
    lines.append(f"Source: {feed.label}")
    # Slim props only — do not copy raw ArcGIS fields (bloats the WS payload).
    props = {
        "zone_code": code,
        "category": category,
        "fillColor": color,
        "source": feed.label,
        "popup": "<br>".join(lines),
    }
    return {"type": "Feature", "geometry": geom, "properties": props}

def _normalize_features(
    raw_features: list[Any], feed: ZoningFeed
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    for feat in raw_features:
        if not isinstance(feat, dict):
            continue
        norm = normalize_zoning_feature(feat, feed)
        if norm:
            features.append(norm)
    return features

def _query_zoning_near_pin(
    feed: ZoningFeed,
    lat: float,
    lng: float,
    *,
    half_span_deg: float,
) -> tuple[list[dict[str, Any]], bool, float, tuple[float, float, float, float]]:
    """Query feed around the pin; keep the largest complete (non-truncated) bbox.

    Dense cities (Santa Monica SCAG) exceed MAX_FEATURES inside a ~2.8 mi box.
    ArcGIS returns the first N records by OBJECTID — often far from the pin — so a
    truncated reply can paint another neighborhood while the pin sits empty.

    Strategy: if the requested span truncates, binary-search the largest span that
    returns a complete result (up to MAX_FEATURES parcels, still centered on pin).
    """

    def _attempt(span: float) -> tuple[list[dict[str, Any]], bool, tuple[float, float, float, float]]:
        box = bbox_around(lat, lng, span)
        raw = _query_arcgis_geojson(feed, box)
        feats = _normalize_features(list(raw.get("features") or []), feed)
        trunc = bool(raw.get("exceededTransferLimit"))
        return feats, trunc, box

    span = float(half_span_deg)
    features, truncated, bbox = _attempt(span)
    if not truncated:
        return features, truncated, span, bbox

    # Requested span overflowed — search largest complete span in [MIN, span].
    lo = MIN_HALF_SPAN_DEG
    hi = span
    best_feats, best_trunc, best_box = _attempt(lo)
    best_span = lo
    if not best_trunc:
        # Expand toward hi with a few binary probes (ArcGIS round-trips).
        for _ in range(6):
            mid = (lo + hi) / 2.0
            feats, trunc, box = _attempt(mid)
            if trunc:
                hi = mid
            else:
                lo = mid
                best_feats, best_trunc, best_box, best_span = feats, trunc, box, mid
        return best_feats, best_trunc, best_span, best_box

    # Even MIN span truncates — return it (still pin-centered).
    return best_feats, best_trunc, best_span, best_box

def build_zoning_geojson(
    city: str | None,
    lat: float,
    lng: float,
    *,
    half_span_deg: float = DEFAULT_HALF_SPAN_DEG,
) -> dict[str, Any]:
    """FeatureCollection of zoning polygons near the pin."""
    primary = resolve_zoning_feed(city, lat, lng)
    if primary is None:
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "feed_id": None,
                "feed_label": None,
                "count": 0,
                "message": (
                    "No zoning layer for this area — v1 covers City of Los Angeles, "
                    "Santa Monica, and unincorporated LA County."
                ),
            },
        }

    feeds_to_try = [primary]
    # Incorporated LA County cities: DRP is empty → SCAG fallback.
    if primary.id == "la_county":
        feeds_to_try.append(FEEDS["scag_la"])
    # Empty city string resolved to la_city: if empty, try county then SCAG.
    if primary.id == "la_city" and not (normalize_city(city)):
        feeds_to_try.extend([FEEDS["la_county"], FEEDS["scag_la"]])

    last_error = ""
    for feed in feeds_to_try:
        key = cache_key(
            "zoning",
            feed.id,
            f"{lat:.3f}",
            f"{lng:.3f}",
            f"{half_span_deg:.3f}",
            CACHE_REV,  # pin-focused shrink when truncated
        )
        cached = read_json("zoning", key, max_age_s=CACHE_MAX_AGE_S)
        if isinstance(cached, dict) and cached.get("type") == "FeatureCollection":
            if (cached.get("features") or []) or feed is feeds_to_try[-1]:
                return cached

        try:
            features, truncated, used_span, bbox = _query_zoning_near_pin(
                feed, lat, lng, half_span_deg=half_span_deg
            )
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            continue

        # ~69 mi per degree latitude; caption for the query half-span (not map zoom).
        radius_mi = used_span * 69.0
        if features:
            msg = (
                f"Zoning: {len(features)} parcels ({feed.label}) "
                f"· ~{radius_mi:.1f} mi radius"
            )
            if truncated:
                msg += f" · truncated at {MAX_FEATURES}"
            if abs(used_span - half_span_deg) > 1e-9:
                msg += " · tightened to pin"
        else:
            msg = (
                "No zoning polygons returned for this pin "
                "(may be outside this feed’s coverage)."
            )

        result = {
            "type": "FeatureCollection",
            "features": features,
            "meta": {
                "feed_id": feed.id,
                "feed_label": feed.label,
                "count": len(features),
                "half_span_deg": used_span,
                "requested_half_span_deg": half_span_deg,
                "truncated": truncated,
                "message": msg,
            },
        }
        if features:
            write_json("zoning", key, result)
            return result
        # Keep empty cached only for last attempt to avoid poisoning fallbacks.
        if feed is feeds_to_try[-1]:
            write_json("zoning", key, result)
            if last_error and not features:
                result["meta"]["message"] = (
                    f"{result['meta']['message']} ({last_error})"
                    if last_error
                    else result["meta"]["message"]
                )
            return result

    return {
        "type": "FeatureCollection",
        "features": [],
        "meta": {
            "feed_id": primary.id,
            "feed_label": primary.label,
            "count": 0,
            "message": last_error or "Zoning query failed.",
        },
    }
