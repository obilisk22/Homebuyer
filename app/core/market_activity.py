"""ZIP-level “Active market” chip from Redfin monthly homes_sold (TODO-051).

Uses the same Redfin Data Center ZIP market tracker as the Map sale-price
choropleth (``redfin_sales.py``). No API key.

**Metric:** latest monthly All-Residential ``homes_sold`` for the property ZIP.
**Active when:** ``homes_sold >= max(ACTIVE_HOMES_SOLD_FLOOR, national P75)``
where P75 is computed across all ZIPs in the cached tracker ingest.

Quiet / missing Redfin rows → no chip (never invent activity).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict

from app.core.models import Property
from app.core.redfin_sales import load_zip_market_bundle

# Absolute floor so tiny markets never light the chip on a weak P75.
ACTIVE_HOMES_SOLD_FLOOR = 12
PROPERTY_STALE_DAYS = 30
CHIP_KEY = "active_market"
CHIP_ICON = "local_fire_department"
CHIP_TONE = "amenity"  # lime — elevated turnover is a market signal

_ZIP5_RE = re.compile(r"^(\d{5})")


class MarketActivity(TypedDict):
    zip_code: str
    supported: bool
    active: bool
    homes_sold: int | None
    period_end: str
    p75_homes_sold: float | None
    threshold: int | None
    median_sale_price: float | None
    error: str


def empty_activity(*, zip_code: str = "", error: str = "") -> MarketActivity:
    return {
        "zip_code": zip_code or "",
        "supported": False,
        "active": False,
        "homes_sold": None,
        "period_end": "",
        "p75_homes_sold": None,
        "threshold": None,
        "median_sale_price": None,
        "error": error or "",
    }


def normalize_zip(raw: str | None) -> str:
    text = (raw or "").strip()
    m = _ZIP5_RE.match(text)
    return m.group(1) if m else ""


def active_threshold(p75: float | None) -> int:
    """Chip fires at max(floor, ceil(P75))."""
    if p75 is None:
        return ACTIVE_HOMES_SOLD_FLOOR
    try:
        return max(ACTIVE_HOMES_SOLD_FLOOR, int(round(float(p75))))
    except (TypeError, ValueError):
        return ACTIVE_HOMES_SOLD_FLOOR


def is_active_market(homes_sold: int | None, *, p75: float | None) -> bool:
    if homes_sold is None:
        return False
    return int(homes_sold) >= active_threshold(p75)


def compute_market_activity(zip_code: str) -> MarketActivity:
    """Look up Redfin ZIP row; mark active vs national homes_sold P75."""
    z5 = normalize_zip(zip_code)
    if not z5:
        return empty_activity(error="no_zip")
    try:
        bundle = load_zip_market_bundle()
    except Exception as exc:  # noqa: BLE001
        return empty_activity(zip_code=z5, error=f"redfin: {exc}")

    zips = bundle.get("zips") or {}
    p75 = bundle.get("homes_sold_p75")
    try:
        p75_f = float(p75) if p75 is not None else None
    except (TypeError, ValueError):
        p75_f = None

    row = zips.get(z5) if isinstance(zips, dict) else None
    if not isinstance(row, dict):
        return empty_activity(zip_code=z5, error="zip_not_in_redfin")

    homes_raw = row.get("homes_sold")
    homes: int | None
    try:
        homes = int(homes_raw) if homes_raw is not None else None
    except (TypeError, ValueError):
        homes = None

    price = row.get("median_sale_price")
    try:
        price_f = float(price) if price is not None else None
    except (TypeError, ValueError):
        price_f = None

    threshold = active_threshold(p75_f)
    active = is_active_market(homes, p75=p75_f)
    return {
        "zip_code": z5,
        "supported": homes is not None,
        "active": active,
        "homes_sold": homes,
        "period_end": str(row.get("period_end") or "").strip(),
        "p75_homes_sold": p75_f,
        "threshold": threshold,
        "median_sale_price": price_f,
        "error": "" if homes is not None else "no_homes_sold",
    }


def parse_activity_json(raw: str | None) -> MarketActivity:
    if not raw or not str(raw).strip():
        return empty_activity()
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return empty_activity(error="bad_json")
    if not isinstance(data, dict):
        return empty_activity(error="bad_json")
    homes = data.get("homes_sold")
    try:
        homes_i = int(homes) if homes is not None else None
    except (TypeError, ValueError):
        homes_i = None
    p75 = data.get("p75_homes_sold")
    try:
        p75_f = float(p75) if p75 is not None else None
    except (TypeError, ValueError):
        p75_f = None
    thr = data.get("threshold")
    try:
        thr_i = int(thr) if thr is not None else None
    except (TypeError, ValueError):
        thr_i = None
    price = data.get("median_sale_price")
    try:
        price_f = float(price) if price is not None else None
    except (TypeError, ValueError):
        price_f = None
    return {
        "zip_code": str(data.get("zip_code") or ""),
        "supported": bool(data.get("supported")),
        "active": bool(data.get("active")),
        "homes_sold": homes_i,
        "period_end": str(data.get("period_end") or ""),
        "p75_homes_sold": p75_f,
        "threshold": thr_i,
        "median_sale_price": price_f,
        "error": str(data.get("error") or ""),
    }


def tooltip_for(activity: MarketActivity | dict[str, Any] | None) -> str:
    if not activity:
        return "Active market"
    homes = activity.get("homes_sold")
    z5 = activity.get("zip_code") or ""
    period = (activity.get("period_end") or "").strip()
    parts: list[str] = []
    if homes is not None and z5:
        parts.append(f"{int(homes)} sales last month in ZIP {z5}")
    elif z5:
        parts.append(f"ZIP {z5}")
    else:
        parts.append("Elevated recent sales")
    if period:
        parts.append(f"period end {period}")
    thr = activity.get("threshold")
    if thr is not None:
        parts.append(f"threshold ≥{int(thr)}")
    return " · ".join(parts)


def chip_spec_for(
    activity: MarketActivity | dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not activity:
        return None
    if not activity.get("supported"):
        return None
    if not activity.get("active"):
        return None
    if activity.get("error") and activity.get("homes_sold") is None:
        return None
    return {
        "key": CHIP_KEY,
        "icon": CHIP_ICON,
        "tone": CHIP_TONE,
        "kind": CHIP_TONE,
        "tooltip": tooltip_for(activity),
        "homes_sold": activity.get("homes_sold"),
    }


def refresh_property_market_activity(prop: Property) -> MarketActivity:
    """Compute and cache market activity on a property without committing."""
    z5 = normalize_zip(getattr(prop, "zip_code", None) or "")
    if not z5:
        payload = empty_activity(error="no_zip")
    else:
        payload = compute_market_activity(z5)
    prop.market_activity = json.dumps(payload)
    prop.market_activity_at = datetime.now(timezone.utc).isoformat()
    return payload


def is_stale(market_activity_at: str | None, *, now: datetime | None = None) -> bool:
    if not market_activity_at or not str(market_activity_at).strip():
        return True
    try:
        ts = datetime.fromisoformat(str(market_activity_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    ref = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ref - ts > timedelta(days=PROPERTY_STALE_DAYS)


def needs_refresh(
    market_activity_at: str | None,
    market_activity: str | None = None,
    *,
    now: datetime | None = None,
) -> bool:
    if is_stale(market_activity_at, now=now):
        return True
    payload = parse_activity_json(market_activity)
    # Retry when last run failed to resolve a homes_sold count.
    if payload.get("error") and payload.get("homes_sold") is None:
        return True
    return False
