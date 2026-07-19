"""FCC Broadband Data Collection (BDC) availability for library risk chips.

Risk rule (TODO-042): show a magenta risk chip only when the census block
reports **no fixed broadband** (copper/DSL, cable, fiber, or terrestrial fixed
wireless). Cable or DSL without fiber is **not** flagged — only total absence
of fixed service. Satellite-only does not clear the risk.

API (no key required):
1. ``geo.fcc.gov`` census block FIPS from lat/lng (2020 blocks).
2. Esri Living Atlas FeatureServer ``FCC_Broadband_Data_Collection_December_2024_View``
   layer 4 (Blocks) — BDC-derived ``UniqueProviders*`` by tech.

The official BDC Public Data API (``broadbandmap.fcc.gov/api/public/map``) is
bulk-download only and needs free ``username`` + ``hash_value`` headers — not
used for per-home lookups. Optional env vars are documented in ``.env.example``
for future bulk ingest only. See docs/RESEARCH.md.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, TypedDict

import requests

from app.core import overlay_cache

if TYPE_CHECKING:
    from app.core.models import Property

STALE_MAX_AGE_DAYS = 30.0
CACHE_NAMESPACE = "fcc_broadband"
RAW_CACHE_MAX_AGE_S = 7 * 24 * 3600
REQUEST_TIMEOUT_S = 30
USER_AGENT = "Homebuy/0.1 (local research app)"

# Documented for RESEARCH / tests — bulk Public Data API (auth required).
BDC_PUBLIC_MAP_BASE = "https://broadbandmap.fcc.gov/api/public/map"
GEO_BLOCK_URL = "https://geo.fcc.gov/api/census/block/find"

# Living Atlas "FCC Broadband Data Collection December 2025 (Latest)" view —
# BDC block summaries (UniqueProviders by tech). No API key.
BDC_BLOCKS_URL = (
    "https://services8.arcgis.com/peDZJliSvYims39Q/arcgis/rest/services/"
    "FCC_Broadband_Data_Collection_December_2024_View/FeatureServer/4/query"
)
BDC_SOURCE_LABEL = "Living Atlas BDC block summary"

CHIP_KEY = "no_broadband"
CHIP_ICON = "wifi_off"
CHIP_KIND = "risk"

# Fixed terrestrial techs in BDC UniqueProviders* fields (excludes satellite).
_FIXED_PROVIDER_FIELDS = (
    ("providers_copper", "UniqueProvidersCopper", "DSL/copper"),
    ("providers_cable", "UniqueProvidersCable", "Cable"),
    ("providers_fiber", "UniqueProvidersFiber", "Fiber"),
    ("providers_ltfw", "UniqueProvidersLTFW", "Fixed wireless"),
    ("providers_lbrtfw", "UniqueProvidersLBRTFW", "Licensed-by-rule FW"),
)


class BroadbandStatus(TypedDict, total=False):
    status: str  # ok | missing | unknown | error
    reason: str
    has_fixed: bool | None
    block_geoid: str
    block_fips: str  # alias of block_geoid for older callers/tests
    total_bsls: int | None
    served_bsls: int | None
    underserved_bsls: int | None
    unserved_bsls: int | None
    providers_copper: int
    providers_cable: int
    providers_fiber: int
    providers_ltfw: int
    providers_lbrtfw: int
    tech_summary: str
    source: str
    error: str


def empty_status(
    *,
    status: str = "unknown",
    reason: str = "",
    has_fixed: bool | None = None,
    error: str | None = None,
) -> BroadbandStatus:
    out: BroadbandStatus = {
        "status": status,
        "reason": reason,
        "has_fixed": has_fixed,
        "block_geoid": "",
        "block_fips": "",
        "total_bsls": None,
        "served_bsls": None,
        "underserved_bsls": None,
        "unserved_bsls": None,
        "providers_copper": 0,
        "providers_cable": 0,
        "providers_fiber": 0,
        "providers_ltfw": 0,
        "providers_lbrtfw": 0,
        "tech_summary": "",
        "source": BDC_SOURCE_LABEL,
    }
    if error:
        out["error"] = error
    return out


def _error_message(exc: BaseException) -> str:
    msg = str(exc).strip() or type(exc).__name__
    return msg[:240]


def _as_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def tech_summary_from_counts(
    *,
    copper: int = 0,
    cable: int = 0,
    fiber: int = 0,
    ltfw: int = 0,
    lbrtfw: int = 0,
) -> str:
    """Human tech list for tooltips (fixed only; satellite omitted)."""
    parts: list[str] = []
    if fiber:
        parts.append("Fiber")
    if cable:
        parts.append("Cable")
    if copper:
        parts.append("DSL/copper")
    if ltfw or lbrtfw:
        parts.append("Fixed wireless")
    return ", ".join(parts) if parts else "None"


def has_fixed_broadband(
    *,
    copper: int = 0,
    cable: int = 0,
    fiber: int = 0,
    ltfw: int = 0,
    lbrtfw: int = 0,
) -> bool:
    """True when any fixed (non-satellite) provider is reported in the block."""
    return (copper + cable + fiber + ltfw + lbrtfw) > 0


def is_broadband_risk(status: BroadbandStatus | dict[str, Any] | None) -> bool:
    """Risk chip only when we positively know fixed service is absent."""
    if not status:
        return False
    if status.get("status") in {"unknown", "error"}:
        return False
    return status.get("has_fixed") is False


def resolve_block_geoid(lat: float, lng: float) -> str:
    """15-digit 2020 census block FIPS via FCC Geo API (no auth)."""
    key = overlay_cache.cache_key("block", f"{lat:.5f}", f"{lng:.5f}")
    cached = overlay_cache.read_json(CACHE_NAMESPACE, key, max_age_s=RAW_CACHE_MAX_AGE_S)
    if isinstance(cached, dict) and cached.get("block_geoid"):
        return str(cached["block_geoid"])

    resp = requests.get(
        GEO_BLOCK_URL,
        params={
            "latitude": lat,
            "longitude": lng,
            "format": "json",
            "censusYear": 2020,
        },
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    payload = resp.json()
    block = payload.get("Block") or {}
    geoid = str(block.get("FIPS") or "").strip()
    if len(geoid) < 15:
        raise ValueError("Could not resolve census block for this pin")
    overlay_cache.write_json(
        CACHE_NAMESPACE,
        key,
        {"block_geoid": geoid, "raw": payload},
    )
    return geoid


# Alias used by some call sites / older tests.
resolve_block_fips = resolve_block_geoid


def _fetch_block_attrs(block_geoid: str) -> dict[str, Any]:
    key = overlay_cache.cache_key("bdc_block", block_geoid)
    cached = overlay_cache.read_json(CACHE_NAMESPACE, key, max_age_s=RAW_CACHE_MAX_AGE_S)
    if isinstance(cached, dict) and cached.get("attributes"):
        attrs = cached["attributes"]
        if isinstance(attrs, dict):
            return attrs

    fields = (
        "GEOID,TotalBSLs,UnservedBSLs,UnderservedBSLs,ServedBSLs,"
        "UniqueProviders,UniqueProvidersCopper,UniqueProvidersCable,"
        "UniqueProvidersFiber,UniqueProvidersLTFW,UniqueProvidersLBRTFW"
    )
    resp = requests.get(
        BDC_BLOCKS_URL,
        params={
            "where": f"GEOID='{block_geoid}'",
            "outFields": fields,
            "returnGeometry": "false",
            "f": "json",
        },
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("error"):
        raise ValueError(str(payload["error"]))
    features = payload.get("features") or []
    if not features:
        raise ValueError(f"No BDC block summary for GEOID {block_geoid}")
    attrs = features[0].get("attributes") or {}
    if not isinstance(attrs, dict):
        raise ValueError("Malformed BDC block feature")
    overlay_cache.write_json(
        CACHE_NAMESPACE,
        key,
        {"attributes": attrs, "raw": payload},
    )
    return attrs


def status_from_block_attrs(attrs: dict[str, Any], *, block_geoid: str = "") -> BroadbandStatus:
    """Map Living Atlas UniqueProviders* fields → compact BroadbandStatus."""
    counts: dict[str, int] = {}
    for out_key, field, _label in _FIXED_PROVIDER_FIELDS:
        counts[out_key] = _as_int(attrs.get(field))

    copper = counts["providers_copper"]
    cable = counts["providers_cable"]
    fiber = counts["providers_fiber"]
    ltfw = counts["providers_ltfw"]
    lbrtfw = counts["providers_lbrtfw"]
    fixed = has_fixed_broadband(
        copper=copper, cable=cable, fiber=fiber, ltfw=ltfw, lbrtfw=lbrtfw
    )
    geoid = str(attrs.get("GEOID") or block_geoid or "").strip()
    return {
        "status": "ok" if fixed else "missing",
        "reason": "living_atlas_bdc_block",
        "has_fixed": fixed,
        "block_geoid": geoid,
        "block_fips": geoid,
        "total_bsls": _as_optional_int(attrs.get("TotalBSLs")),
        "served_bsls": _as_optional_int(attrs.get("ServedBSLs")),
        "underserved_bsls": _as_optional_int(attrs.get("UnderservedBSLs")),
        "unserved_bsls": _as_optional_int(attrs.get("UnservedBSLs")),
        "providers_copper": copper,
        "providers_cable": cable,
        "providers_fiber": fiber,
        "providers_ltfw": ltfw,
        "providers_lbrtfw": lbrtfw,
        "tech_summary": tech_summary_from_counts(
            copper=copper, cable=cable, fiber=fiber, ltfw=ltfw, lbrtfw=lbrtfw
        ),
        "source": BDC_SOURCE_LABEL,
    }


def compute_broadband(lat: float, lng: float) -> BroadbandStatus:
    """Resolve block + BDC summary. Raises on hard failures (caller may catch)."""
    geoid = resolve_block_geoid(lat, lng)
    attrs = _fetch_block_attrs(geoid)
    return status_from_block_attrs(attrs, block_geoid=geoid)


def compute_broadband_status(lat: float, lng: float) -> BroadbandStatus:
    """Never-raises wrapper used by property refresh paths."""
    try:
        return compute_broadband(lat, lng)
    except Exception as exc:  # noqa: BLE001
        return empty_status(
            status="error",
            reason="compute_failed",
            error=_error_message(exc),
        )


def lookup_broadband(
    *,
    lat: float | None = None,
    lng: float | None = None,
    address: str | None = None,
) -> BroadbandStatus:
    """Query fixed broadband availability; never raises — returns unknown on failure.

    Prefers lat/lng. When only ``address`` is given, geocodes via the app geocoder.
    """
    try:
        pin_lat = float(lat) if lat is not None else None
        pin_lng = float(lng) if lng is not None else None
    except (TypeError, ValueError):
        pin_lat, pin_lng = None, None

    if pin_lat is None or pin_lng is None:
        addr = (address or "").strip()
        if not addr:
            return empty_status(reason="no_input", error="No coordinates or address")
        try:
            from app.core.geocode import geocode_address

            pin_lat, pin_lng = geocode_address(addr)
        except Exception as exc:  # noqa: BLE001
            return empty_status(reason="geocode_failed", error=_error_message(exc))

    return compute_broadband_status(float(pin_lat), float(pin_lng))


def parse_status_json(raw: str | None) -> BroadbandStatus:
    if not raw or not str(raw).strip():
        return empty_status(reason="empty")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return empty_status(status="error", reason="bad_json", error="invalid JSON")
    if not isinstance(data, dict):
        return empty_status(status="error", reason="bad_json", error="not an object")
    out = empty_status()
    for key in list(out.keys()):
        if key in data:
            out[key] = data[key]  # type: ignore[literal-required]
    if data.get("error"):
        out["error"] = str(data["error"])
    # Prefer block_geoid; accept legacy block_fips.
    geoid = str(out.get("block_geoid") or data.get("block_fips") or "").strip()
    out["block_geoid"] = geoid
    out["block_fips"] = geoid
    for k in (
        "providers_copper",
        "providers_cable",
        "providers_fiber",
        "providers_ltfw",
        "providers_lbrtfw",
    ):
        out[k] = _as_int(out.get(k))  # type: ignore[literal-required]
    hf = out.get("has_fixed")
    if hf is not None:
        out["has_fixed"] = bool(hf)
    status = str(out.get("status") or "unknown")
    if status not in {"ok", "missing", "unknown", "error"}:
        status = "unknown"
    out["status"] = status
    return out


def refresh_property_broadband(prop: Property) -> BroadbandStatus:
    """Compute and cache broadband status on a property without committing."""
    if prop.latitude is None or prop.longitude is None:
        return parse_status_json(getattr(prop, "broadband_status", None))
    try:
        payload = compute_broadband(float(prop.latitude), float(prop.longitude))
    except Exception as exc:  # noqa: BLE001
        payload = empty_status(
            status="error", reason="compute_failed", error=_error_message(exc)
        )
    prop.broadband_status = json.dumps(payload)
    prop.broadband_at = datetime.now(timezone.utc).isoformat()
    return payload


def is_stale(
    broadband_at: str | None,
    *,
    now: datetime | None = None,
    max_age_days: float = STALE_MAX_AGE_DAYS,
) -> bool:
    if not broadband_at or not str(broadband_at).strip():
        return True
    now = now or datetime.now(timezone.utc)
    try:
        ts = datetime.fromisoformat(str(broadband_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_days = (now - ts).total_seconds() / 86400.0
    return age_days > max_age_days


def needs_refresh(
    broadband_at: str | None,
    broadband_status: str | None = None,
    *,
    now: datetime | None = None,
) -> bool:
    if is_stale(broadband_at, now=now):
        return True
    payload = parse_status_json(broadband_status)
    if payload.get("error"):
        return True
    if payload.get("status") in {"unknown", "error"}:
        return True
    return False


def tooltip_for(status: BroadbandStatus | dict[str, Any] | None) -> str:
    if not status or status.get("has_fixed") is not False:
        return "No fixed broadband reported"
    tech = str(status.get("tech_summary") or "").strip()
    if tech and tech != "None":
        return f"No fixed broadband · {tech}"
    return "No fixed broadband reported"


def broadband_risk_chip(prop: Any) -> tuple[str, dict[str, Any]] | None:
    """UI helper: ``(key, entry)`` when the property lacks fixed broadband."""
    status = parse_status_json(getattr(prop, "broadband_status", None))
    if not is_broadband_risk(status):
        return None
    entry = {
        "hit": True,
        "risk": True,
        "icon": CHIP_ICON,
        "kind": CHIP_KIND,
        "tooltip": tooltip_for(status),
        "tech_summary": status.get("tech_summary") or "None",
        "block_geoid": status.get("block_geoid") or status.get("block_fips") or "",
        "has_fixed": False,
        "source": status.get("source") or BDC_SOURCE_LABEL,
    }
    return CHIP_KEY, entry


def chip_spec_for(status: BroadbandStatus | dict[str, Any] | None) -> dict[str, Any] | None:
    """RiskChip-shaped dict for ``listing_risk_chips`` / pages listing_chips."""
    if not is_broadband_risk(status):
        return None
    return {
        "key": CHIP_KEY,
        "kind": CHIP_KIND,
        "icon": CHIP_ICON,
        "tooltip": tooltip_for(status),
    }


def broadband_risk_entry(prop: Any) -> dict[str, Any] | None:
    """Chip dict for listing_risk_chips / pages wiring (alias of chip_spec_for)."""
    return chip_spec_for(parse_status_json(getattr(prop, "broadband_status", None)))
