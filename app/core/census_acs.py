"""Census ACS median household income (B19013) + nearby tract GeoJSON."""

from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv

from app.core.overlay_cache import cache_key, read_json, write_json

load_dotenv()

REQUEST_TIMEOUT_S = 30
ACS_YEAR = 2023
ACS_DATASET = f"{ACS_YEAR}/acs/acs5"
# Cache ACS + geometries for a week.
CACHE_MAX_AGE_S = 7 * 24 * 3600

# Approximate degrees for ~3 mile / 5 km radius around pin.
DEFAULT_HALF_SPAN_DEG = 0.045

# Choropleth breaks (USD median household income) → fill colors (cyberpunk-ish).
INCOME_BREAKS: list[tuple[float, str]] = [
    (40_000, "#1a237e"),
    (60_000, "#283593"),
    (80_000, "#00838f"),
    (100_000, "#00E5FF"),
    (150_000, "#B8FF3C"),
    (float("inf"), "#FF2BD6"),
]

INCOME_LEGEND: list[tuple[str, str]] = [
    ("< $40k", "#1a237e"),
    ("$40–60k", "#283593"),
    ("$60–80k", "#00838f"),
    ("$80–100k", "#00E5FF"),
    ("$100–150k", "#B8FF3C"),
    ("$150k+", "#FF2BD6"),
]


class CensusKeyMissing(Exception):
    """Raised when CENSUS_API_KEY is not configured."""


def census_api_key() -> str:
    return (os.getenv("CENSUS_API_KEY") or "").strip()


def has_census_key() -> bool:
    return bool(census_api_key())


def bbox_around(lat: float, lng: float, half_span_deg: float = DEFAULT_HALF_SPAN_DEG) -> tuple[float, float, float, float]:
    """Return (min_lng, min_lat, max_lng, max_lat)."""
    return (lng - half_span_deg, lat - half_span_deg, lng + half_span_deg, lat + half_span_deg)


def income_fill_color(value: float | None) -> str:
    if value is None:
        return "#2A3340"
    for threshold, color in INCOME_BREAKS:
        if value < threshold:
            return color
    return INCOME_BREAKS[-1][1]


def parse_acs_tract_rows(rows: list[list[str]]) -> dict[str, float | None]:
    """Map GEOID (11-digit state+county+tract) → median income from ACS table rows."""
    if not rows:
        return {}
    header, *data = rows
    try:
        name_i = header.index("NAME")
        val_i = header.index("B19013_001E")
        state_i = header.index("state")
        county_i = header.index("county")
        tract_i = header.index("tract")
    except ValueError as exc:
        raise ValueError(f"Unexpected ACS header: {header}") from exc

    out: dict[str, float | None] = {}
    for row in data:
        geoid = f"{row[state_i]}{row[county_i]}{row[tract_i]}"
        raw = row[val_i]
        if raw in (None, "", "-", "null", "-666666666", "-999999999"):
            out[geoid] = None
        else:
            try:
                out[geoid] = float(raw)
            except ValueError:
                out[geoid] = None
        _ = name_i  # header validated
    return out


def _fcc_fips(lat: float, lng: float) -> tuple[str, str]:
    """Return (state_fips, county_fips) via FCC block API (no key)."""
    key = cache_key("fcc", f"{lat:.4f}", f"{lng:.4f}")
    cached = read_json("fcc_fips", key, max_age_s=CACHE_MAX_AGE_S)
    if isinstance(cached, dict) and cached.get("state") and cached.get("county"):
        return str(cached["state"]), str(cached["county"])

    url = "https://geo.fcc.gov/api/census/block/find"
    resp = requests.get(
        url,
        params={"latitude": lat, "longitude": lng, "format": "json"},
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    payload = resp.json()
    block = payload.get("Block") or {}
    fips = str(block.get("FIPS") or "")
    if len(fips) < 5:
        county = payload.get("County") or {}
        state = payload.get("State") or {}
        state_fips = str(state.get("FIPS") or "").zfill(2)
        county_fips = str(county.get("FIPS") or "").zfill(3)
    else:
        state_fips = fips[:2]
        county_fips = fips[2:5]
    if not state_fips or not county_fips:
        raise ValueError("Could not resolve census FIPS for this pin")
    write_json("fcc_fips", key, {"state": state_fips, "county": county_fips})
    return state_fips, county_fips


def _fetch_acs_incomes(state_fips: str, county_fips: str) -> dict[str, float | None]:
    key = cache_key("acs", ACS_YEAR, state_fips, county_fips, "B19013")
    cached = read_json("acs_income", key, max_age_s=CACHE_MAX_AGE_S)
    if isinstance(cached, dict):
        return {str(k): (float(v) if v is not None else None) for k, v in cached.items()}

    api_key = census_api_key()
    if not api_key:
        raise CensusKeyMissing(
            "Add CENSUS_API_KEY to .env (free at https://api.census.gov/data/key_signup.html)"
        )

    url = f"https://api.census.gov/data/{ACS_DATASET}"
    resp = requests.get(
        url,
        params={
            "get": "NAME,B19013_001E",
            "for": "tract:*",
            "in": f"state:{state_fips} county:{county_fips}",
            "key": api_key,
        },
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    incomes = parse_acs_tract_rows(resp.json())
    write_json("acs_income", key, incomes)
    return incomes


def _fetch_tract_geojson(bbox: tuple[float, float, float, float], state_fips: str, county_fips: str) -> dict[str, Any]:
    min_lng, min_lat, max_lng, max_lat = bbox
    key = cache_key(
        "tiger",
        state_fips,
        county_fips,
        f"{min_lng:.3f}",
        f"{min_lat:.3f}",
        f"{max_lng:.3f}",
        f"{max_lat:.3f}",
    )
    cached = read_json("tiger_tracts", key, max_age_s=CACHE_MAX_AGE_S)
    if isinstance(cached, dict) and cached.get("type") == "FeatureCollection":
        return cached

    # TIGERweb Current Tracts layer — bbox query, GeoJSON out.
    url = (
        "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
        "Tracts_Blocks/MapServer/7/query"
    )
    geometry = f"{min_lng},{min_lat},{max_lng},{max_lat}"
    resp = requests.get(
        url,
        params={
            "where": f"STATE='{state_fips}' AND COUNTY='{county_fips}'",
            "geometry": geometry,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "GEOID,STATE,COUNTY,TRACT,BASENAME,NAME",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
        },
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict):
        raise ValueError("Unexpected TIGER response")
    write_json("tiger_tracts", key, payload)
    return payload


def build_income_geojson(
    lat: float,
    lng: float,
    *,
    half_span_deg: float = DEFAULT_HALF_SPAN_DEG,
) -> dict[str, Any]:
    """FeatureCollection of nearby tracts with median income + fillColor."""
    state_fips, county_fips = _fcc_fips(lat, lng)
    bbox = bbox_around(lat, lng, half_span_deg)
    incomes = _fetch_acs_incomes(state_fips, county_fips)
    geo = _fetch_tract_geojson(bbox, state_fips, county_fips)

    features: list[dict[str, Any]] = []
    for feat in geo.get("features") or []:
        props = dict(feat.get("properties") or {})
        geoid = str(props.get("GEOID") or "")
        if not geoid:
            state = str(props.get("STATE") or state_fips).zfill(2)
            county = str(props.get("COUNTY") or county_fips).zfill(3)
            tract = str(props.get("TRACT") or "").zfill(6)
            geoid = f"{state}{county}{tract}"
        income = incomes.get(geoid)
        color = income_fill_color(income)
        label = f"${income:,.0f}" if income is not None else "N/A"
        name = props.get("NAME") or props.get("BASENAME") or geoid
        props.update(
            {
                "GEOID": geoid,
                "median_income": income,
                "fillColor": color,
                "popup": f"{name}<br>Median HH income: {label}",
            }
        )
        features.append(
            {
                "type": "Feature",
                "geometry": feat.get("geometry"),
                "properties": props,
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "state_fips": state_fips,
            "county_fips": county_fips,
            "variable": "B19013_001E",
            "year": ACS_YEAR,
        },
    }
