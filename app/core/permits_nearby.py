"""Nearby building-permit activity (Socrata SODA) for library risk chips.

Supported cities: City of Los Angeles, Seattle, Austin.
High activity: >= HIGH_ACTIVITY_THRESHOLD matching permits within RADIUS_MI
issued in the last WINDOW_MONTHS. See docs/RESEARCH.md (TODO-043).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, TypedDict

import requests
from dotenv import load_dotenv

from app.core import overlay_cache
from app.core.geo import haversine_miles, normalize_city, point_in_bbox

if TYPE_CHECKING:
    from app.core.models import Property

load_dotenv()

RADIUS_MI = 0.25
RADIUS_M = int(round(RADIUS_MI * 1609.344))  # ~402 m for SODA within_circle
WINDOW_MONTHS = 24
HIGH_ACTIVITY_THRESHOLD = 8
STALE_MAX_AGE_DAYS = 30.0
CACHE_NAMESPACE = "permits"
RAW_CACHE_MAX_AGE_S = 7 * 24 * 3600
REQUEST_TIMEOUT_S = 30
MAX_ROWS = 200
CHIP_ICON = "construction"
CHIP_TONE = "amber"  # attention / construction risk — not magenta crime risk

# Rough metro bboxes for pin fallback when city string is empty/ambiguous.
_LA_CITY_BBOX = (33.70, 34.35, -118.67, -118.15)
_SEATTLE_BBOX = (47.45, 47.80, -122.45, -122.20)
_AUSTIN_BBOX = (30.08, 30.52, -97.95, -97.55)

_CANCELLED_STATUS_FRAGMENTS = (
    "withdraw",
    "cancel",
    "denied",
    "refund",
    "void",
    "not required",
)


class PermitHit(TypedDict, total=False):
    type: str
    status: str
    issued: str
    lat: float
    lng: float
    distance_mi: float


class PermitActivity(TypedDict, total=False):
    city: str
    supported: bool
    high_activity: bool
    count: int
    radius_mi: float
    window_months: int
    threshold: int
    nearest_distance_mi: float | None
    sample_types: list[str]
    error: str


@dataclass(frozen=True)
class PermitCityConfig:
    key: str
    label: str
    domain: str
    dataset: str
    location_field: str
    lat_field: str
    lng_field: str
    date_field: str
    type_field: str
    status_field: str
    aliases: frozenset[str]
    metro_bbox: tuple[float, float, float, float]
    # SoQL fragment ANDed into $where (no leading AND).
    type_where: str


PERMIT_CITIES: dict[str, PermitCityConfig] = {
    "los_angeles": PermitCityConfig(
        key="los_angeles",
        label="Los Angeles",
        domain="data.lacity.org",
        dataset="pi9x-tg5x",
        location_field="geolocation",
        lat_field="lat",
        lng_field="lon",
        date_field="issue_date",
        type_field="permit_type",
        status_field="status_desc",
        aliases=frozenset(
            {
                "los angeles",
                "la",
                "city of los angeles",
                "hollywood",
                "echo park",
                "silver lake",
                "los feliz",
                "highland park",
                "eagle rock",
                "studio city",
                "sherman oaks",
                "encino",
                "van nuys",
                "north hollywood",
                "hollywood hills",
                "westwood",
                "brentwood",
                "pacific palisades",
                "mar vista",
                "venice",
                "san pedro",
                "wilmington",
                "harbor city",
                "canoga park",
                "reseda",
                "northridge",
                "chatsworth",
                "woodland hills",
                "tujunga",
                "sunland",
                "sylmar",
                "pacoima",
                "panorama city",
                "mission hills",
                "granada hills",
                "porter ranch",
                "westchester",
                "playa del rey",
                "playa vista",
                "palms",
                "mid-city",
                "mid city",
                "koreatown",
                "downtown los angeles",
                "dtla",
                "boyle heights",
                "lincoln heights",
                "el sereno",
                "atwater village",
                "glassell park",
                "mount washington",
                "mt washington",
                "cypress park",
                "arlington heights",
                "westlake",
                "pico-union",
                "university park",
                "exposition park",
                "leimert park",
                "crenshaw",
                "hyde park",
                "watts",
            }
        ),
        metro_bbox=_LA_CITY_BBOX,
        # Building / non-building structural + grading; dataset has no electrical group.
        type_where=(
            "(starts_with(permit_type, 'Bldg-') OR starts_with(permit_type, 'Nonbldg-') "
            "OR permit_type = 'Grading' OR upper(permit_type) like '%DEMOLITION%')"
        ),
    ),
    "seattle": PermitCityConfig(
        key="seattle",
        label="Seattle",
        domain="data.seattle.gov",
        dataset="76t5-zqzr",
        location_field="location1",
        lat_field="latitude",
        lng_field="longitude",
        date_field="issueddate",
        type_field="permittypemapped",
        status_field="statuscurrent",
        aliases=frozenset({"seattle"}),
        metro_bbox=_SEATTLE_BBOX,
        type_where="permittypemapped in ('Building', 'Demolition', 'Grading')",
    ),
    "austin": PermitCityConfig(
        key="austin",
        label="Austin",
        domain="data.austintexas.gov",
        dataset="3syk-w9eu",
        location_field="location",
        lat_field="latitude",
        lng_field="longitude",
        date_field="issue_date",
        type_field="permit_type_desc",
        status_field="status_current",
        aliases=frozenset({"austin"}),
        metro_bbox=_AUSTIN_BBOX,
        type_where="permit_type_desc in ('Building Permit', 'Electrical Permit')",
    ),
}


def socrata_app_token() -> str:
    return (os.getenv("SOCRATA_APP_TOKEN") or "").strip()


def resolve_permit_city(
    city: str | None,
    lat: float | None = None,
    lng: float | None = None,
) -> PermitCityConfig | None:
    """Return the SODA feed for this pin, or None when unsupported."""
    norm = normalize_city(city)
    if norm:
        for cfg in PERMIT_CITIES.values():
            if norm in cfg.aliases:
                return cfg
    if lat is not None and lng is not None:
        for cfg in PERMIT_CITIES.values():
            if point_in_bbox(float(lat), float(lng), cfg.metro_bbox):
                return cfg
    return None


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "Homebuy/0.1 (local research app)",
    }
    token = socrata_app_token()
    if token:
        headers["X-App-Token"] = token
    return headers


def _window_since(*, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    # Approximate months as 30.44 days.
    return now - timedelta(days=int(WINDOW_MONTHS * 30.44))


def _error_message(exc: BaseException) -> str:
    msg = str(exc).strip() or exc.__class__.__name__
    return msg[:240]


def _status_cancelled(status: str) -> bool:
    low = (status or "").strip().lower()
    if not low:
        return False
    return any(frag in low for frag in _CANCELLED_STATUS_FRAGMENTS)


def _parse_row(row: dict[str, Any], cfg: PermitCityConfig) -> PermitHit | None:
    try:
        plat = float(row.get(cfg.lat_field))
        plng = float(row.get(cfg.lng_field))
    except (TypeError, ValueError):
        return None
    if plat == 0 and plng == 0:
        return None
    status = str(row.get(cfg.status_field) or "").strip()
    if _status_cancelled(status):
        return None
    ptype = str(row.get(cfg.type_field) or "").strip() or "Permit"
    issued = str(row.get(cfg.date_field) or "").strip()
    return {
        "type": ptype,
        "status": status,
        "issued": issued,
        "lat": plat,
        "lng": plng,
    }


def _type_matches_client(cfg: PermitCityConfig, ptype: str) -> bool:
    """Extra client filter when SoQL type_where is absent or rows are unfiltered."""
    t = (ptype or "").strip()
    if cfg.key == "los_angeles":
        return (
            t.startswith("Bldg-")
            or t.startswith("Nonbldg-")
            or t == "Grading"
            or "demolition" in t.lower()
        )
    if cfg.key == "seattle":
        return t in {"Building", "Demolition", "Grading"}
    if cfg.key == "austin":
        return t in {"Building Permit", "Electrical Permit"}
    return True


def _soda_fetch(
    cfg: PermitCityConfig,
    lat: float,
    lng: float,
    *,
    since: datetime,
    limit: int = MAX_ROWS,
) -> list[dict[str, Any]]:
    since_day = since.strftime("%Y-%m-%dT00:00:00.000")
    where = (
        f"within_circle({cfg.location_field}, {lat}, {lng}, {RADIUS_M}) "
        f"AND {cfg.date_field} >= '{since_day}' "
        f"AND {cfg.type_where}"
    )
    params = {
        "$where": where,
        "$order": f"{cfg.date_field} DESC",
        "$limit": str(int(limit)),
    }
    cache_key = overlay_cache.cache_key(
        "soda",
        cfg.dataset,
        f"{lat:.5f}",
        f"{lng:.5f}",
        str(RADIUS_M),
        since_day[:10],
        str(limit),
    )
    cached = overlay_cache.read_json(
        CACHE_NAMESPACE, cache_key, max_age_s=RAW_CACHE_MAX_AGE_S
    )
    if isinstance(cached, list):
        return cached

    url = f"https://{cfg.domain}/resource/{cfg.dataset}.json"
    resp = requests.get(
        url, params=params, headers=_headers(), timeout=REQUEST_TIMEOUT_S
    )
    resp.raise_for_status()
    rows = resp.json()
    if not isinstance(rows, list):
        rows = []
    overlay_cache.write_json(CACHE_NAMESPACE, cache_key, rows)
    return rows


def empty_activity(
    *,
    city: str = "",
    supported: bool = False,
    error: str | None = None,
) -> PermitActivity:
    out: PermitActivity = {
        "city": city,
        "supported": supported,
        "high_activity": False,
        "count": 0,
        "radius_mi": RADIUS_MI,
        "window_months": WINDOW_MONTHS,
        "threshold": HIGH_ACTIVITY_THRESHOLD,
        "nearest_distance_mi": None,
        "sample_types": [],
    }
    if error:
        out["error"] = error
    return out


def compute_permit_activity(
    lat: float,
    lng: float,
    *,
    city: str | None = None,
    now: datetime | None = None,
) -> PermitActivity:
    """Query SODA and return a compact activity payload for persistence."""
    cfg = resolve_permit_city(city, lat, lng)
    if cfg is None:
        return empty_activity(city="", supported=False)

    since = _window_since(now=now)
    try:
        rows = _soda_fetch(cfg, float(lat), float(lng), since=since)
    except Exception as exc:  # noqa: BLE001 - never break add-home
        return empty_activity(
            city=cfg.key, supported=True, error=_error_message(exc)
        )

    hits: list[PermitHit] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        hit = _parse_row(row, cfg)
        if hit is None:
            continue
        if not _type_matches_client(cfg, hit.get("type") or ""):
            continue
        dist = haversine_miles(float(lat), float(lng), hit["lat"], hit["lng"])
        if dist > RADIUS_MI + 1e-6:
            continue
        hit["distance_mi"] = round(dist, 4)
        hits.append(hit)

    hits.sort(key=lambda h: float(h.get("distance_mi") or 999.0))
    count = len(hits)
    sample: list[str] = []
    seen: set[str] = set()
    for h in hits:
        t = str(h.get("type") or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        sample.append(t)
        if len(sample) >= 3:
            break

    nearest = float(hits[0]["distance_mi"]) if hits else None
    return {
        "city": cfg.key,
        "supported": True,
        "high_activity": count >= HIGH_ACTIVITY_THRESHOLD,
        "count": count,
        "radius_mi": RADIUS_MI,
        "window_months": WINDOW_MONTHS,
        "threshold": HIGH_ACTIVITY_THRESHOLD,
        "nearest_distance_mi": nearest,
        "sample_types": sample,
    }


def parse_activity_json(raw: str | None) -> PermitActivity:
    if not raw or not str(raw).strip():
        return empty_activity()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return empty_activity()
    if not isinstance(data, dict):
        return empty_activity()
    out = empty_activity()
    for key in out:
        if key in data:
            out[key] = data[key]  # type: ignore[literal-required]
    if "error" in data and data["error"]:
        out["error"] = str(data["error"])
    # Coerce common fields.
    out["supported"] = bool(out.get("supported"))
    out["high_activity"] = bool(out.get("high_activity"))
    try:
        out["count"] = int(out.get("count") or 0)
    except (TypeError, ValueError):
        out["count"] = 0
    samples = out.get("sample_types") or []
    if not isinstance(samples, list):
        samples = []
    out["sample_types"] = [str(s) for s in samples if str(s).strip()][:5]
    return out


def refresh_property_permits(prop: Property) -> PermitActivity:
    """Compute and cache permit activity on a property without committing."""
    if prop.latitude is None or prop.longitude is None:
        return parse_activity_json(getattr(prop, "permits_activity", None))
    city = getattr(prop, "city", None) or ""
    try:
        payload = compute_permit_activity(
            float(prop.latitude),
            float(prop.longitude),
            city=city,
        )
    except Exception as exc:  # noqa: BLE001
        payload = empty_activity(
            city=normalize_city(city) or "",
            supported=True,
            error=_error_message(exc),
        )
    prop.permits_activity = json.dumps(payload)
    prop.permits_activity_at = datetime.now(timezone.utc).isoformat()
    return payload


def is_stale(
    permits_activity_at: str | None,
    *,
    now: datetime | None = None,
    max_age_days: float = STALE_MAX_AGE_DAYS,
) -> bool:
    if not permits_activity_at or not str(permits_activity_at).strip():
        return True
    now = now or datetime.now(timezone.utc)
    try:
        ts = datetime.fromisoformat(str(permits_activity_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_days = (now - ts).total_seconds() / 86400.0
    return age_days > max_age_days


def needs_refresh(
    permits_activity_at: str | None,
    permits_activity: str | None = None,
    *,
    now: datetime | None = None,
) -> bool:
    if is_stale(permits_activity_at, now=now):
        return True
    payload = parse_activity_json(permits_activity)
    if payload.get("error"):
        return True
    return False


def tooltip_for(activity: PermitActivity | dict[str, Any] | None) -> str:
    """Human tooltip for the high-permits chip (count + nearest distance)."""
    if not activity:
        return "High permit activity nearby"
    count = int(activity.get("count") or 0)
    months = int(activity.get("window_months") or WINDOW_MONTHS)
    radius = float(activity.get("radius_mi") or RADIUS_MI)
    nearest = activity.get("nearest_distance_mi")
    samples = activity.get("sample_types") or []
    parts = [f"{count} permits ≤ {radius:g} mi · {months} mo"]
    if nearest is not None:
        try:
            parts.append(f"nearest {float(nearest):.2f} mi")
        except (TypeError, ValueError):
            pass
    if samples:
        parts.append(", ".join(str(s) for s in samples[:3]))
    return " · ".join(parts)


def chip_spec_for(
    activity: PermitActivity | dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return chip dict for library/header wiring, or None when no chip.

    UI (pages.py) should render when this returns a dict::

        {"key": "permits", "icon": "construction", "tone": "amber",
         "tooltip": "...", "count": N}
    """
    if not activity:
        return None
    if not activity.get("supported"):
        return None
    if not activity.get("high_activity"):
        return None
    if activity.get("error") and int(activity.get("count") or 0) <= 0:
        return None
    return {
        "key": "permits",
        "icon": CHIP_ICON,
        "tone": CHIP_TONE,
        "tooltip": tooltip_for(activity),
        "count": int(activity.get("count") or 0),
        "nearest_distance_mi": activity.get("nearest_distance_mi"),
    }
