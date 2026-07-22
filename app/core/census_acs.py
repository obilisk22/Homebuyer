"""Census ACS tract choropleths near a pin (income, home value, age, kids/HH)."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests
from dotenv import load_dotenv

from app.core.cache import memo_get, memo_set, quantize_geojson, singleflight
from app.core.overlay_cache import cache_key, read_json, write_json

load_dotenv()

REQUEST_TIMEOUT_S = 30
ACS_YEAR = 2023
ACS_DATASET = f"{ACS_YEAR}/acs/acs5"
CACHE_MAX_AGE_S = 7 * 24 * 3600
MEMO_TTL_S = 3600.0
STYLED_MEMO_NS = "acs_styled"
STYLED_CACHE_REV = "q1"
DEFAULT_HALF_SPAN_DEG = 0.045

_MISSING = {None, "", "-", "null", "-666666666", "-999999999"}


@dataclass(frozen=True)
class AcsLayerConfig:
    id: str
    legend_title: str
    legend: list[tuple[str, str]]
    breaks: list[tuple[float, str]]
    get_vars: list[str]
    cache_tag: str
    variable_label: str
    parse: Callable[[list[list[str]]], dict[str, float | None]]
    format_value: Callable[[float | None], str]
    popup_metric: str


class CensusKeyMissing(Exception):
    """Raised when CENSUS_API_KEY is not configured."""


def census_api_key() -> str:
    return (os.getenv("CENSUS_API_KEY") or "").strip()


def has_census_key() -> bool:
    return bool(census_api_key())


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


def fill_color_for_breaks(value: float | None, breaks: list[tuple[float, str]]) -> str:
    if value is None:
        return "#2A3340"
    for threshold, color in breaks:
        if value < threshold:
            return color
    return breaks[-1][1]


def _cell_float(raw: object) -> float | None:
    if raw in _MISSING:
        return None
    try:
        val = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if val <= -1_000_000:
        return None
    return val


def _header_indexes(header: list[str], *names: str) -> dict[str, int]:
    try:
        return {n: header.index(n) for n in names}
    except ValueError as exc:
        raise ValueError(f"Unexpected ACS header: {header}") from exc


def parse_acs_single_var(rows: list[list[str]], var: str) -> dict[str, float | None]:
    """GEOID → float for a single ACS estimate column."""
    if not rows:
        return {}
    header, *data = rows
    idx = _header_indexes(header, "NAME", var, "state", "county", "tract")
    out: dict[str, float | None] = {}
    for row in data:
        geoid = f"{row[idx['state']]}{row[idx['county']]}{row[idx['tract']]}"
        out[geoid] = _cell_float(row[idx[var]])
    return out


def parse_acs_tract_rows(rows: list[list[str]]) -> dict[str, float | None]:
    """Compat: GEOID → median income (B19013)."""
    raw = parse_acs_single_var(rows, "B19013_001E")
    return {k: (v if v is not None and v > 0 else None) for k, v in raw.items()}


def parse_acs_avg_kids_rows(rows: list[list[str]]) -> dict[str, float | None]:
    """Children under 18 per occupied household (B09001 / B25003)."""
    if not rows:
        return {}
    header, *data = rows
    idx = _header_indexes(
        header, "NAME", "B09001_001E", "B25003_001E", "state", "county", "tract"
    )
    out: dict[str, float | None] = {}
    for row in data:
        geoid = f"{row[idx['state']]}{row[idx['county']]}{row[idx['tract']]}"
        kids = _cell_float(row[idx["B09001_001E"]])
        hh = _cell_float(row[idx["B25003_001E"]])
        if kids is None or hh is None or hh <= 0 or kids < 0:
            out[geoid] = None
        else:
            out[geoid] = kids / hh
    return out


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

HOME_VALUE_BREAKS: list[tuple[float, str]] = [
    (400_000, "#1a237e"),
    (600_000, "#4a148c"),
    (800_000, "#7b1fa2"),
    (1_000_000, "#00E5FF"),
    (1_500_000, "#B8FF3C"),
    (float("inf"), "#FF2BD6"),
]

HOME_VALUE_LEGEND: list[tuple[str, str]] = [
    ("< $400k", "#1a237e"),
    ("$400–600k", "#4a148c"),
    ("$600–800k", "#7b1fa2"),
    ("$800k–1M", "#00E5FF"),
    ("$1–1.5M", "#B8FF3C"),
    ("$1.5M+", "#FF2BD6"),
]

MEDIAN_AGE_BREAKS: list[tuple[float, str]] = [
    (30, "#00838f"),
    (35, "#00ACC1"),
    (40, "#00E5FF"),
    (45, "#B8FF3C"),
    (50, "#FFC107"),
    (float("inf"), "#FF2BD6"),
]

MEDIAN_AGE_LEGEND: list[tuple[str, str]] = [
    ("< 30", "#00838f"),
    ("30–35", "#00ACC1"),
    ("35–40", "#00E5FF"),
    ("40–45", "#B8FF3C"),
    ("45–50", "#FFC107"),
    ("50+", "#FF2BD6"),
]

AVG_KIDS_BREAKS: list[tuple[float, str]] = [
    (0.3, "#1a237e"),
    (0.6, "#283593"),
    (0.9, "#7b1fa2"),
    (1.2, "#FF2BD6"),
    (float("inf"), "#B8FF3C"),
]

AVG_KIDS_LEGEND: list[tuple[str, str]] = [
    ("< 0.3", "#1a237e"),
    ("0.3–0.6", "#283593"),
    ("0.6–0.9", "#7b1fa2"),
    ("0.9–1.2", "#FF2BD6"),
    ("1.2+", "#B8FF3C"),
]

OWNER_OCC_BREAKS: list[tuple[float, str]] = [
    (40, "#1a237e"),
    (55, "#283593"),
    (70, "#00838f"),
    (85, "#00E5FF"),
    (float("inf"), "#B8FF3C"),
]

OWNER_OCC_LEGEND: list[tuple[str, str]] = [
    ("< 40%", "#1a237e"),
    ("40–55%", "#283593"),
    ("55–70%", "#00838f"),
    ("70–85%", "#00E5FF"),
    ("85%+", "#B8FF3C"),
]

YEAR_BUILT_BREAKS: list[tuple[float, str]] = [
    (1960, "#4a148c"),
    (1980, "#7b1fa2"),
    (2000, "#00838f"),
    (2010, "#00E5FF"),
    (float("inf"), "#B8FF3C"),
]

YEAR_BUILT_LEGEND: list[tuple[str, str]] = [
    ("Before 1960", "#4a148c"),
    ("1960–79", "#7b1fa2"),
    ("1980–99", "#00838f"),
    ("2000–09", "#00E5FF"),
    ("2010+", "#B8FF3C"),
]

GROSS_RENT_BREAKS: list[tuple[float, str]] = [
    (1_500, "#1a237e"),
    (2_000, "#283593"),
    (2_500, "#00838f"),
    (3_000, "#00E5FF"),
    (4_000, "#B8FF3C"),
    (float("inf"), "#FF2BD6"),
]

GROSS_RENT_LEGEND: list[tuple[str, str]] = [
    ("< $1.5k", "#1a237e"),
    ("$1.5–2k", "#283593"),
    ("$2–2.5k", "#00838f"),
    ("$2.5–3k", "#00E5FF"),
    ("$3–4k", "#B8FF3C"),
    ("$4k+", "#FF2BD6"),
]

BACHELORS_BREAKS: list[tuple[float, str]] = [
    (20, "#1a237e"),
    (35, "#283593"),
    (50, "#00838f"),
    (65, "#00E5FF"),
    (float("inf"), "#B8FF3C"),
]

BACHELORS_LEGEND: list[tuple[str, str]] = [
    ("< 20%", "#1a237e"),
    ("20–35%", "#283593"),
    ("35–50%", "#00838f"),
    ("50–65%", "#00E5FF"),
    ("65%+", "#B8FF3C"),
]


def _fmt_dollars(value: float | None) -> str:
    return f"${value:,.0f}" if value is not None else "N/A"


def _fmt_years(value: float | None) -> str:
    return f"{value:.1f} years" if value is not None else "N/A"


def _fmt_kids(value: float | None) -> str:
    return f"{value:.2f} kids/HH" if value is not None else "N/A"


def _fmt_percent(value: float | None) -> str:
    return f"{value:.0f}%" if value is not None else "N/A"


def _fmt_year_built(value: float | None) -> str:
    return f"{value:.0f}" if value is not None else "N/A"


def _parse_home_value(rows: list[list[str]]) -> dict[str, float | None]:
    raw = parse_acs_single_var(rows, "B25077_001E")
    return {k: (v if v is not None and v > 0 else None) for k, v in raw.items()}


def _parse_median_age(rows: list[list[str]]) -> dict[str, float | None]:
    raw = parse_acs_single_var(rows, "B01002_001E")
    return {k: (v if v is not None and v > 0 else None) for k, v in raw.items()}


def parse_acs_owner_occ_pct_rows(rows: list[list[str]]) -> dict[str, float | None]:
    """% owner-occupied of occupied housing units (B25003_002 / B25003_001 × 100)."""
    if not rows:
        return {}
    header, *data = rows
    idx = _header_indexes(
        header, "NAME", "B25003_001E", "B25003_002E", "state", "county", "tract"
    )
    out: dict[str, float | None] = {}
    for row in data:
        geoid = f"{row[idx['state']]}{row[idx['county']]}{row[idx['tract']]}"
        total = _cell_float(row[idx["B25003_001E"]])
        owners = _cell_float(row[idx["B25003_002E"]])
        if total is None or owners is None or total <= 0 or owners < 0:
            out[geoid] = None
        else:
            out[geoid] = 100.0 * owners / total
    return out


def parse_acs_year_built_rows(rows: list[list[str]]) -> dict[str, float | None]:
    raw = parse_acs_single_var(rows, "B25035_001E")
    # Census year-built medians are calendar years (e.g. 1974).
    return {k: (v if v is not None and 1600 < v < 2100 else None) for k, v in raw.items()}


def parse_acs_gross_rent_rows(rows: list[list[str]]) -> dict[str, float | None]:
    raw = parse_acs_single_var(rows, "B25064_001E")
    return {k: (v if v is not None and v > 0 else None) for k, v in raw.items()}


def parse_acs_bachelors_pct_rows(rows: list[list[str]]) -> dict[str, float | None]:
    """% of adults 25+ with bachelor's or higher (B15003)."""
    if not rows:
        return {}
    header, *data = rows
    idx = _header_indexes(
        header,
        "NAME",
        "B15003_001E",
        "B15003_022E",
        "B15003_023E",
        "B15003_024E",
        "B15003_025E",
        "state",
        "county",
        "tract",
    )
    out: dict[str, float | None] = {}
    for row in data:
        geoid = f"{row[idx['state']]}{row[idx['county']]}{row[idx['tract']]}"
        total = _cell_float(row[idx["B15003_001E"]])
        parts = [
            _cell_float(row[idx["B15003_022E"]]),
            _cell_float(row[idx["B15003_023E"]]),
            _cell_float(row[idx["B15003_024E"]]),
            _cell_float(row[idx["B15003_025E"]]),
        ]
        if total is None or total <= 0 or any(p is None or p < 0 for p in parts):
            out[geoid] = None
        else:
            out[geoid] = 100.0 * sum(parts) / total  # type: ignore[arg-type]
    return out


ACS_LAYERS: dict[str, AcsLayerConfig] = {
    "income": AcsLayerConfig(
        id="income",
        legend_title="Median household income (ACS tracts)",
        legend=INCOME_LEGEND,
        breaks=INCOME_BREAKS,
        get_vars=["B19013_001E"],
        cache_tag="B19013",
        variable_label="B19013",
        parse=parse_acs_tract_rows,
        format_value=_fmt_dollars,
        popup_metric="Median HH income",
    ),
    "home_value": AcsLayerConfig(
        id="home_value",
        legend_title="Median home value (ACS tracts)",
        legend=HOME_VALUE_LEGEND,
        breaks=HOME_VALUE_BREAKS,
        get_vars=["B25077_001E"],
        cache_tag="B25077",
        variable_label="B25077",
        parse=_parse_home_value,
        format_value=_fmt_dollars,
        popup_metric="Median home value",
    ),
    "median_age": AcsLayerConfig(
        id="median_age",
        legend_title="Median age (ACS tracts)",
        legend=MEDIAN_AGE_LEGEND,
        breaks=MEDIAN_AGE_BREAKS,
        get_vars=["B01002_001E"],
        cache_tag="B01002",
        variable_label="B01002",
        parse=_parse_median_age,
        format_value=_fmt_years,
        popup_metric="Median age",
    ),
    "avg_kids": AcsLayerConfig(
        id="avg_kids",
        legend_title="Avg kids under 18 per household (ACS)",
        legend=AVG_KIDS_LEGEND,
        breaks=AVG_KIDS_BREAKS,
        get_vars=["B09001_001E", "B25003_001E"],
        cache_tag="B09001_B25003",
        variable_label="B09001/B25003",
        parse=parse_acs_avg_kids_rows,
        format_value=_fmt_kids,
        popup_metric="Children under 18 per occupied HH",
    ),
    "owner_occ": AcsLayerConfig(
        id="owner_occ",
        legend_title="% owner-occupied (ACS tracts)",
        legend=OWNER_OCC_LEGEND,
        breaks=OWNER_OCC_BREAKS,
        get_vars=["B25003_001E", "B25003_002E"],
        cache_tag="B25003_owner_pct",
        variable_label="B25003",
        parse=parse_acs_owner_occ_pct_rows,
        format_value=_fmt_percent,
        popup_metric="% owner-occupied",
    ),
    "year_built": AcsLayerConfig(
        id="year_built",
        legend_title="Median year structure built (ACS)",
        legend=YEAR_BUILT_LEGEND,
        breaks=YEAR_BUILT_BREAKS,
        get_vars=["B25035_001E"],
        cache_tag="B25035",
        variable_label="B25035",
        parse=parse_acs_year_built_rows,
        format_value=_fmt_year_built,
        popup_metric="Median year built",
    ),
    "gross_rent": AcsLayerConfig(
        id="gross_rent",
        legend_title="Median gross rent (ACS tracts)",
        legend=GROSS_RENT_LEGEND,
        breaks=GROSS_RENT_BREAKS,
        get_vars=["B25064_001E"],
        cache_tag="B25064",
        variable_label="B25064",
        parse=parse_acs_gross_rent_rows,
        format_value=_fmt_dollars,
        popup_metric="Median gross rent",
    ),
    "bachelors": AcsLayerConfig(
        id="bachelors",
        legend_title="% bachelor's or higher age 25+ (ACS)",
        legend=BACHELORS_LEGEND,
        breaks=BACHELORS_BREAKS,
        get_vars=[
            "B15003_001E",
            "B15003_022E",
            "B15003_023E",
            "B15003_024E",
            "B15003_025E",
        ],
        cache_tag="B15003_bachelors_pct",
        variable_label="B15003",
        parse=parse_acs_bachelors_pct_rows,
        format_value=_fmt_percent,
        popup_metric="% bachelor's+",
    ),
}


def _parse_acs_missing(raw: object) -> float | None:
    if raw is None or raw == "" or raw is False:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val < -1_000_000:
        return None
    if val <= 0:
        return None
    return val


def _county_median_gross_rent(
    state_fips: str, county_fips: str, year: int
) -> float | None:
    key = cache_key("acs", year, state_fips, county_fips, "B25064_county")
    cached = read_json("acs_county_rent", key, max_age_s=CACHE_MAX_AGE_S)
    if isinstance(cached, dict) and "rent" in cached:
        rent = cached.get("rent")
        return float(rent) if rent is not None else None

    dataset = f"{year}/acs/acs5"
    url = f"https://api.census.gov/data/{dataset}"
    params = {
        "get": "NAME,B25064_001E",
        "for": f"county:{county_fips}",
        "in": f"state:{state_fips}",
        "key": census_api_key(),
    }
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        rows = resp.json()
    except Exception:
        return None

    if not isinstance(rows, list) or len(rows) < 2:
        return None
    header, data = rows[0], rows[1]
    try:
        rent_i = header.index("B25064_001E")
        rent = _parse_acs_missing(data[rent_i])
    except (IndexError, ValueError):
        return None
    write_json(
        "acs_county_rent",
        key,
        {"rent": rent, "name": data[header.index("NAME")] if "NAME" in header else ""},
    )
    return rent


def county_median_rent_cagr(lat: float, lng: float) -> float | None:
    """Return the five-year CAGR of county median gross rent (ACS B25064)."""
    from app.core.finance import rent_cagr_pct

    if not has_census_key():
        return None
    try:
        state_fips, county_fips = _fcc_fips(lat, lng)
    except Exception:
        return None

    end = _county_median_gross_rent(state_fips, county_fips, ACS_YEAR)
    start = _county_median_gross_rent(state_fips, county_fips, ACS_YEAR - 5)
    if end is None or start is None:
        return None
    return rent_cagr_pct(start, end, years=5)


def county_effective_property_tax_rate(lat: float, lng: float) -> float | None:
    """Median real-estate taxes / median home value for the pin's county (ACS 5-year)."""
    if not has_census_key():
        return None
    try:
        state_fips, county_fips = _fcc_fips(lat, lng)
    except Exception:
        return None

    key = cache_key("acs", ACS_YEAR, state_fips, county_fips, "B25103_B25077")
    cached = read_json("acs_tax_rate", key, max_age_s=CACHE_MAX_AGE_S)
    if isinstance(cached, dict) and "rate" in cached:
        rate = cached.get("rate")
        return float(rate) if rate is not None else None

    url = f"https://api.census.gov/data/{ACS_DATASET}"
    params = {
        "get": "NAME,B25103_001E,B25077_001E",
        "for": f"county:{county_fips}",
        "in": f"state:{state_fips}",
        "key": census_api_key(),
    }
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        rows = resp.json()
    except Exception:
        return None

    if not isinstance(rows, list) or len(rows) < 2:
        return None
    header, data = rows[0], rows[1]
    try:
        tax_i = header.index("B25103_001E")
        val_i = header.index("B25077_001E")
    except ValueError:
        return None
    median_tax = _parse_acs_missing(data[tax_i])
    median_value = _parse_acs_missing(data[val_i])
    rate: float | None = None
    if median_tax is not None and median_value is not None and median_value > 0:
        rate = median_tax / median_value
    write_json(
        "acs_tax_rate",
        key,
        {
            "rate": rate,
            "median_tax": median_tax,
            "median_value": median_value,
            "name": data[header.index("NAME")] if "NAME" in header else "",
        },
    )
    return rate


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


def _fetch_acs_values(
    layer: AcsLayerConfig, state_fips: str, county_fips: str
) -> dict[str, float | None]:
    key = cache_key("acs", ACS_YEAR, state_fips, county_fips, layer.cache_tag)
    cached = read_json(f"acs_{layer.id}", key, max_age_s=CACHE_MAX_AGE_S)
    if isinstance(cached, dict):
        return {str(k): (float(v) if v is not None else None) for k, v in cached.items()}

    api_key = census_api_key()
    if not api_key:
        raise CensusKeyMissing(
            "Add CENSUS_API_KEY to .env (free at https://api.census.gov/data/key_signup.html)"
        )

    get_cols = ",".join(["NAME", *layer.get_vars])
    url = f"https://api.census.gov/data/{ACS_DATASET}"
    resp = requests.get(
        url,
        params={
            "get": get_cols,
            "for": "tract:*",
            "in": f"state:{state_fips} county:{county_fips}",
            "key": api_key,
        },
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    values = layer.parse(resp.json())
    write_json(f"acs_{layer.id}", key, values)
    return values


def _fetch_tract_geojson(
    bbox: tuple[float, float, float, float], state_fips: str, county_fips: str
) -> dict[str, Any]:
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


def _safe_quantize(fc: dict[str, Any]) -> dict[str, Any]:
    """Round/dedupe coords; on failure return the pre-quantize payload."""
    try:
        return quantize_geojson(fc, precision=5)
    except Exception:  # noqa: BLE001
        return fc


def _styled_memo_key(
    layer_id: str, lat: float, lng: float, half_span_deg: float
) -> str:
    return cache_key(
        STYLED_CACHE_REV,
        layer_id,
        f"{lat:.3f}",
        f"{lng:.3f}",
        f"{half_span_deg:.3f}",
    )


def _build_acs_geojson_uncached(
    layer_id: str,
    lat: float,
    lng: float,
    *,
    half_span_deg: float,
) -> dict[str, Any]:
    layer = ACS_LAYERS.get(layer_id)
    if layer is None:
        raise ValueError(f"Unknown ACS layer: {layer_id}")

    state_fips, county_fips = _fcc_fips(lat, lng)
    bbox = bbox_around(lat, lng, half_span_deg)
    values = _fetch_acs_values(layer, state_fips, county_fips)
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
        value = values.get(geoid)
        color = fill_color_for_breaks(value, layer.breaks)
        label = layer.format_value(value)
        name = props.get("NAME") or props.get("BASENAME") or geoid
        props.update(
            {
                "GEOID": geoid,
                "acs_value": value,
                "fillColor": color,
                "popup": f"{name}<br>{layer.popup_metric}: {label}",
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
            "variable": layer.variable_label,
            "year": ACS_YEAR,
            "layer_id": layer_id,
        },
    }


def build_acs_geojson(
    layer_id: str,
    lat: float,
    lng: float,
    *,
    half_span_deg: float = DEFAULT_HALF_SPAN_DEG,
) -> dict[str, Any]:
    """FeatureCollection of nearby tracts for an ACS choropleth layer.

    Styled output is quantized (precision 5) and memoized per layer+bbox so Map
    re-toggles skip rebuild. Quantize failure falls back to the unsimplified FC.
    """
    if layer_id not in ACS_LAYERS:
        raise ValueError(f"Unknown ACS layer: {layer_id}")

    key = _styled_memo_key(layer_id, lat, lng, half_span_deg)
    memoed = memo_get(STYLED_MEMO_NS, key)
    if isinstance(memoed, dict) and memoed.get("type") == "FeatureCollection":
        return memoed

    def factory() -> dict[str, Any]:
        hit = memo_get(STYLED_MEMO_NS, key)
        if isinstance(hit, dict) and hit.get("type") == "FeatureCollection":
            return hit
        result = _safe_quantize(
            _build_acs_geojson_uncached(
                layer_id, lat, lng, half_span_deg=half_span_deg
            )
        )
        memo_set(STYLED_MEMO_NS, key, result, ttl_s=MEMO_TTL_S)
        return result

    return singleflight(STYLED_MEMO_NS, key, factory)
