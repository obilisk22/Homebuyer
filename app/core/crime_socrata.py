"""Crime near pin — LA County (LAPD + Santa Monica) and Seattle."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import requests
from dotenv import load_dotenv

from app.core.geo import normalize_city, point_in_bbox
from app.core.overlay_cache import cache_key, read_json, write_json

load_dotenv()

REQUEST_TIMEOUT_S = 30
CACHE_MAX_AGE_S = 6 * 3600  # 6 hours
DEFAULT_HALF_SPAN_DEG = 0.02  # ~1.4 miles
# Wide window — city open-data feeds can lag months behind "today".
DEFAULT_DAYS = 365
MAX_ROWS = 500
# Over-fetch when filtering bbox client-side (text lat/lng columns).
CLIENT_FILTER_FETCH = 2000

FeedKind = Literal["socrata", "ckan"]

# Mainland Los Angeles County (approx). Catalina omitted.
LA_COUNTY_BBOX: tuple[float, float, float, float] = (33.45, 34.85, -118.95, -117.65)

# Common LA County cities + neighborhoods for city-name enablement.
LA_COUNTY_PLACE_NAMES: frozenset[str] = frozenset(
    {
        "acton",
        "agoura hills",
        "agua dulce",
        "alhambra",
        "altadena",
        "arcadia",
        "azusa",
        "baldwin park",
        "bell",
        "bell gardens",
        "bellflower",
        "beverly hills",
        "boyle heights",
        "bradbury",
        "brentwood",
        "burbank",
        "calabasas",
        "canoga park",
        "canyon country",
        "carson",
        "castaic",
        "century city",
        "chatsworth",
        "cheviot hills",
        "claremont",
        "commerce",
        "compton",
        "covina",
        "cudahy",
        "culver city",
        "del rey",
        "diamond bar",
        "downey",
        "duarte",
        "eagle rock",
        "east la",
        "east los angeles",
        "echo park",
        "el monte",
        "el segundo",
        "encino",
        "gardena",
        "glendale",
        "glendora",
        "granada hills",
        "hacienda heights",
        "harbor city",
        "hawthorne",
        "hermosa beach",
        "hidden hills",
        "highland park",
        "hollywood",
        "huntington park",
        "industry",
        "inglewood",
        "irwindale",
        "koreatown",
        "la",
        "la canada flintridge",
        "la cañada flintridge",
        "la crescenta",
        "la puente",
        "la verne",
        "lakewood",
        "lancaster",
        "lawndale",
        "lennox",
        "lincoln heights",
        "lomita",
        "long beach",
        "los angeles",
        "los feliz",
        "lynwood",
        "malibu",
        "manhattan beach",
        "mar vista",
        "marina del rey",
        "maywood",
        "mid city",
        "mid-city",
        "mission hills",
        "montebello",
        "monterey park",
        "monrovia",
        "montrose",
        "mount washington",
        "mt washington",
        "newhall",
        "north hollywood",
        "northridge",
        "norwalk",
        "ocean park",
        "pacific palisades",
        "pacoima",
        "palmdale",
        "palms",
        "palos verdes estates",
        "panorama city",
        "paramount",
        "pasadena",
        "pico rivera",
        "playa del rey",
        "playa vista",
        "pomona",
        "porter ranch",
        "quartz hill",
        "rancho park",
        "rancho palos verdes",
        "redondo beach",
        "reseda",
        "rolling hills",
        "rolling hills estates",
        "rosemead",
        "rowland heights",
        "san dimas",
        "san fernando",
        "san gabriel",
        "san marino",
        "san pedro",
        "santa clarita",
        "santa monica",
        "santamonica",
        "saugus",
        "sawtelle",
        "sherman oaks",
        "sierra madre",
        "signal hill",
        "silver lake",
        "south el monte",
        "south gate",
        "south pasadena",
        "stevenson ranch",
        "studio city",
        "sun valley",
        "sunland",
        "sunset park",
        "sylmar",
        "tarzana",
        "temple city",
        "torrance",
        "tujunga",
        "valencia",
        "valley village",
        "van nuys",
        "venice",
        "vernon",
        "walnut",
        "west covina",
        "west hollywood",
        "west los angeles",
        "westchester",
        "westlake village",
        "westwood",
        "whittier",
        "wilmington",
        "woodland hills",
        "city of los angeles",
    }
)


@dataclass(frozen=True)
class CrimeCityConfig:
    id: str
    label: str
    kind: FeedKind
    aliases: tuple[str, ...]
    # Approximate metro box (min_lat, max_lat, min_lng, max_lng) for pin fallback.
    metro_bbox: tuple[float, float, float, float]
    # Socrata
    domain: str = ""
    dataset: str = ""
    lat_field: str = ""
    lng_field: str = ""
    date_field: str = ""
    desc_field: str = ""
    coords_numeric: bool = True
    # CKAN (Santa Monica Open Data)
    ckan_base: str = ""
    ckan_resource_id: str = ""


CRIME_CITIES: dict[str, CrimeCityConfig] = {
    "santa_monica": CrimeCityConfig(
        id="santa_monica",
        label="Santa Monica",
        kind="ckan",
        aliases=("santa monica", "santamonica"),
        metro_bbox=(33.98, 34.06, -118.535, -118.44),
        ckan_base="https://data.santamonica.gov/ne/api/3/action",
        ckan_resource_id="ff0f4877-3731-4476-b2ca-065f5819bf12",
        lat_field="latitude",
        lng_field="longitude",
        date_field="date_occurred",
        desc_field="ucr_description",
    ),
    "los_angeles": CrimeCityConfig(
        id="los_angeles",
        label="Los Angeles (LAPD)",
        kind="socrata",
        domain="data.lacity.org",
        dataset="2nrs-mtv8",
        lat_field="lat",
        lng_field="lon",
        date_field="date_occ",
        desc_field="crm_cd_desc",
        aliases=("los angeles", "la", "city of los angeles"),
        metro_bbox=LA_COUNTY_BBOX,
        coords_numeric=True,
    ),
    "seattle": CrimeCityConfig(
        id="seattle",
        label="Seattle",
        kind="socrata",
        domain="data.seattle.gov",
        dataset="tazs-3rd5",
        lat_field="latitude",
        lng_field="longitude",
        date_field="offense_date",
        desc_field="offense_category",
        aliases=("seattle",),
        metro_bbox=(47.45, 47.80, -122.45, -122.20),
        coords_numeric=False,
    ),
}


def socrata_app_token() -> str:
    return (os.getenv("SOCRATA_APP_TOKEN") or "").strip()


def in_la_county(
    city: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
) -> bool:
    """True if city name or pin falls in Los Angeles County."""
    norm = normalize_city(city)
    if norm and (norm in LA_COUNTY_PLACE_NAMES or "los angeles" in norm):
        return True
    if lat is not None and lng is not None:
        return point_in_bbox(float(lat), float(lng), LA_COUNTY_BBOX)
    return False


def resolve_crime_feeds(
    city: str | None,
    lat: float | None = None,
    lng: float | None = None,
) -> list[CrimeCityConfig]:
    """Feeds to query for this pin (may be more than one in LA County)."""
    norm = normalize_city(city)

    if norm in CRIME_CITIES["seattle"].aliases or norm == "seattle":
        return [CRIME_CITIES["seattle"]]
    if lat is not None and lng is not None and point_in_bbox(
        float(lat), float(lng), CRIME_CITIES["seattle"].metro_bbox
    ):
        return [CRIME_CITIES["seattle"]]

    if in_la_county(city, lat, lng):
        # Merge LAPD + Santa Monica PD — densest open feeds in the county.
        return [CRIME_CITIES["los_angeles"], CRIME_CITIES["santa_monica"]]

    return []


def crime_supported(
    city: str | None,
    lat: float | None = None,
    lng: float | None = None,
) -> bool:
    return bool(resolve_crime_feeds(city, lat, lng))


def bbox_around(
    lat: float, lng: float, half_span_deg: float = DEFAULT_HALF_SPAN_DEG
) -> tuple[float, float, float, float]:
    return (lng - half_span_deg, lat - half_span_deg, lng + half_span_deg, lat + half_span_deg)


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "Homebuy/0.1 (local research app)",
    }
    token = socrata_app_token()
    if token:
        headers["X-App-Token"] = token
    return headers


def _parse_point(row: dict[str, Any], cfg: CrimeCityConfig) -> dict[str, Any] | None:
    try:
        plat = float(row.get(cfg.lat_field))
        plng = float(row.get(cfg.lng_field))
    except (TypeError, ValueError):
        return None
    if plat == 0 and plng == 0:
        return None
    # Skip obvious placeholder / out-of-area schema rows (seen in SM CKAN).
    if plat == 39.7817 and plng == -89.6501:
        return None
    return {
        "lat": plat,
        "lng": plng,
        "desc": str(row.get(cfg.desc_field) or "Incident"),
        "when": str(row.get(cfg.date_field) or ""),
    }


def _in_bbox(
    plat: float,
    plng: float,
    bbox: tuple[float, float, float, float],
) -> bool:
    min_lng, min_lat, max_lng, max_lat = bbox
    return min_lat <= plat <= max_lat and min_lng <= plng <= max_lng


def _soda_get(cfg: CrimeCityConfig, params: dict[str, str]) -> list[dict[str, Any]]:
    url = f"https://{cfg.domain}/resource/{cfg.dataset}.json"
    resp = requests.get(url, params=params, headers=_headers(), timeout=REQUEST_TIMEOUT_S)
    resp.raise_for_status()
    rows = resp.json()
    return rows if isinstance(rows, list) else []


def _ckan_get(
    cfg: CrimeCityConfig, lat: float, lng: float, days: int, limit: int
) -> list[dict[str, Any]]:
    """Santa Monica CKAN DataStore — SQL bbox + date filter."""
    min_lng, min_lat, max_lng, max_lat = bbox_around(lat, lng)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_day = since.strftime("%Y-%m-%d")
    rid = cfg.ckan_resource_id
    sql = (
        f'SELECT "{cfg.lat_field}", "{cfg.lng_field}", "{cfg.date_field}", "{cfg.desc_field}" '
        f'FROM "{rid}" '
        f'WHERE "{cfg.lat_field}" IS NOT NULL AND "{cfg.lng_field}" IS NOT NULL '
        f'AND "{cfg.lat_field}" BETWEEN {min_lat} AND {max_lat} '
        f'AND "{cfg.lng_field}" BETWEEN {min_lng} AND {max_lng} '
        f'AND "{cfg.date_field}" >= \'{since_day}\' '
        f'ORDER BY "{cfg.date_field}" DESC '
        f"LIMIT {int(limit)}"
    )
    url = f"{cfg.ckan_base.rstrip('/')}/datastore_search_sql"
    resp = requests.get(url, params={"sql": sql}, headers=_headers(), timeout=REQUEST_TIMEOUT_S)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        raise ValueError(f"CKAN crime query failed: {payload.get('error') or payload}")
    records = (payload.get("result") or {}).get("records") or []
    if records:
        return records if isinstance(records, list) else []

    sql_bbox = (
        f'SELECT "{cfg.lat_field}", "{cfg.lng_field}", "{cfg.date_field}", "{cfg.desc_field}" '
        f'FROM "{rid}" '
        f'WHERE "{cfg.lat_field}" IS NOT NULL AND "{cfg.lng_field}" IS NOT NULL '
        f'AND "{cfg.lat_field}" BETWEEN {min_lat} AND {max_lat} '
        f'AND "{cfg.lng_field}" BETWEEN {min_lng} AND {max_lng} '
        f'ORDER BY "{cfg.date_field}" DESC '
        f"LIMIT {int(limit)}"
    )
    resp2 = requests.get(
        url, params={"sql": sql_bbox}, headers=_headers(), timeout=REQUEST_TIMEOUT_S
    )
    resp2.raise_for_status()
    payload2 = resp2.json()
    if not payload2.get("success"):
        raise ValueError(f"CKAN crime query failed: {payload2.get('error') or payload2}")
    records2 = (payload2.get("result") or {}).get("records") or []
    return records2 if isinstance(records2, list) else []


def _fetch_socrata_rows(
    cfg: CrimeCityConfig,
    lat: float,
    lng: float,
    *,
    days: int,
    limit: int,
    half_span_deg: float,
) -> list[dict[str, Any]]:
    bbox = bbox_around(lat, lng, half_span_deg)
    min_lng, min_lat, max_lng, max_lat = bbox
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%S")
    select = f"{cfg.lat_field},{cfg.lng_field},{cfg.date_field},{cfg.desc_field}"
    points_rows: list[dict[str, Any]] = []

    if cfg.coords_numeric:
        where = (
            f"{cfg.lat_field} between {min_lat} and {max_lat} AND "
            f"{cfg.lng_field} between {min_lng} and {max_lng} AND "
            f"{cfg.date_field} >= '{since_iso}'"
        )
        rows = _soda_get(
            cfg,
            {
                "$select": select,
                "$where": where,
                "$order": f"{cfg.date_field} DESC",
                "$limit": str(limit),
            },
        )
        if not rows:
            where_bbox = (
                f"{cfg.lat_field} between {min_lat} and {max_lat} AND "
                f"{cfg.lng_field} between {min_lng} and {max_lng}"
            )
            rows = _soda_get(
                cfg,
                {
                    "$select": select,
                    "$where": where_bbox,
                    "$order": f"{cfg.date_field} DESC",
                    "$limit": str(limit),
                },
            )
        points_rows = rows
    else:
        where = f"{cfg.date_field} >= '{since_iso}'"
        rows = _soda_get(
            cfg,
            {
                "$select": select,
                "$where": where,
                "$order": f"{cfg.date_field} DESC",
                "$limit": str(CLIENT_FILTER_FETCH),
            },
        )
        if not rows:
            rows = _soda_get(
                cfg,
                {
                    "$select": select,
                    "$order": f"{cfg.date_field} DESC",
                    "$limit": str(CLIENT_FILTER_FETCH),
                },
            )
        for row in rows:
            pt = _parse_point(row, cfg)
            if pt and _in_bbox(pt["lat"], pt["lng"], bbox):
                points_rows.append(row)
            if len(points_rows) >= limit:
                break
    return points_rows


def _rows_for_feed(
    cfg: CrimeCityConfig,
    lat: float,
    lng: float,
    *,
    days: int,
    limit: int,
    half_span_deg: float,
) -> list[dict[str, Any]]:
    if cfg.kind == "ckan":
        return _ckan_get(cfg, lat, lng, days, limit)
    return _fetch_socrata_rows(
        cfg, lat, lng, days=days, limit=limit, half_span_deg=half_span_deg
    )


def fetch_crime_near_pin(
    city: str | None,
    lat: float,
    lng: float,
    *,
    half_span_deg: float = DEFAULT_HALF_SPAN_DEG,
    days: int = DEFAULT_DAYS,
    limit: int = MAX_ROWS,
) -> dict[str, Any]:
    """
    Fetch recent crime points near the pin for a supported metro.

    LA County merges LAPD + Santa Monica PD open feeds (coverage is densest in
    those jurisdictions; other county cities may return fewer nearby points).

    Returns ``{"city": ..., "points": [{"lat","lng","desc","when"}], "message": ...}``.
    """
    feeds = resolve_crime_feeds(city, lat, lng)
    if not feeds:
        return {
            "city": None,
            "points": [],
            "message": (
                "No crime layer for this area "
                "(Los Angeles County and Seattle open data only)."
            ),
        }

    feed_ids = "+".join(c.id for c in feeds)
    key = cache_key(
        "crime",
        feed_ids,
        f"{lat:.3f}",
        f"{lng:.3f}",
        str(days),
        f"{half_span_deg:.3f}",
        "v4-county",
    )
    cached = read_json("crime", key, max_age_s=CACHE_MAX_AGE_S)
    if isinstance(cached, dict) and "points" in cached:
        return cached

    per_feed = max(50, limit // max(1, len(feeds)))
    points: list[dict[str, Any]] = []
    seen: set[tuple[float, float, str]] = set()
    errors: list[str] = []

    for cfg in feeds:
        try:
            rows = _rows_for_feed(
                cfg, lat, lng, days=days, limit=per_feed, half_span_deg=half_span_deg
            )
        except Exception as exc:  # noqa: BLE001 — keep other feeds if one fails
            errors.append(f"{cfg.label}: {exc}")
            continue
        for row in rows:
            pt = _parse_point(row, cfg)
            if not pt:
                continue
            sig = (round(pt["lat"], 5), round(pt["lng"], 5), pt["desc"][:40])
            if sig in seen:
                continue
            seen.add(sig)
            points.append(pt)
            if len(points) >= limit:
                break
        if len(points) >= limit:
            break

    if in_la_county(city, lat, lng):
        label = "LA County (LAPD + Santa Monica PD)"
    else:
        label = feeds[0].label

    message = f"{len(points)} incidents near pin ({label}, last {days} days / recent)."
    if not points and errors:
        message = f"Crime fetch issues: {'; '.join(errors)}"

    result = {
        "city": label,
        "points": points,
        "message": message,
        "source": ", ".join(
            (
                f"{c.ckan_base}/datastore_search_sql"
                if c.kind == "ckan"
                else f"https://{c.domain}/resource/{c.dataset}"
            )
            for c in feeds
        ),
    }
    write_json("crime", key, result)
    return result
