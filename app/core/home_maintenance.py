"""Resolve monthly maintenance / repair budget from age, size, price, and state."""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache

from app.core.paths import package_data_file

_TABLE_PATH = package_data_file("home_maintenance_state_index.json")

# Angi 2024 State of Home Spending (national averages, USD / year)
ANGI_MAINTENANCE_USD = 1750.0
ANGI_EMERGENCY_USD = 978.0

RESERVE_WEIGHT = 0.6
OBSERVED_WEIGHT = 0.4


@lru_cache(maxsize=1)
def _load_table() -> dict:
    with _TABLE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def state_cost_index(state: str | None) -> float:
    """Return home-services cost index vs national (1.0 = average)."""
    st = (state or "").strip().upper()
    table = _load_table()
    default = float(table.get("default_index") or 1.0)
    if len(st) != 2:
        return default
    indexes: dict = table.get("index_by_state") or {}
    raw = indexes.get(st)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def age_band_rates(year_built: int | None) -> tuple[float, float]:
    """Return (fraction of price / year, $/sqft / year) for the home's age.

    Unknown age → mid band (20–39): 1.25% / $1.50.
    """
    if year_built is None:
        return 0.0125, 1.50
    try:
        yb = int(year_built)
    except (TypeError, ValueError):
        return 0.0125, 1.50
    if yb < 1800 or yb > date.today().year + 1:
        return 0.0125, 1.50

    age = max(0, date.today().year - yb)
    if age < 10:
        return 0.0075, 1.00
    if age < 20:
        return 0.0100, 1.25
    if age < 40:
        return 0.0125, 1.50
    return 0.0150, 2.00


def _effective_price(list_price: float | None, offer_price: float | None) -> float:
    offer = float(offer_price or 0)
    if offer > 0:
        return offer
    return max(0.0, float(list_price or 0))


def resolve_monthly_maintenance(
    *,
    list_price: float | None,
    offer_price: float | None = None,
    sqft: float | None,
    year_built: int | None,
    state: str | None,
) -> tuple[float | None, str]:
    """Blend age-based reserve with Angi observed spend × state index.

    ``reserve = average(age_% × price, age_$/sqft × sqft × index)`` when both
    legs exist; otherwise the available leg only.
    ``observed = (1750 + 978) × index``
    ``annual = 0.6 × reserve + 0.4 × observed``

    Returns ``(None, "")`` when neither price nor sqft is available.
    """
    price = _effective_price(list_price, offer_price)
    area = float(sqft or 0)
    if price <= 0 and area <= 0:
        return None, ""

    idx = state_cost_index(state)
    pct, psf = age_band_rates(year_built)

    legs: list[float] = []
    if price > 0:
        legs.append(pct * price)
    if area > 0:
        legs.append(psf * area * idx)
    reserve = sum(legs) / len(legs)

    observed = (ANGI_MAINTENANCE_USD + ANGI_EMERGENCY_USD) * idx
    annual = RESERVE_WEIGHT * reserve + OBSERVED_WEIGHT * observed
    monthly = round(annual / 12.0)

    st = (state or "").strip().upper()
    st_label = st if len(st) == 2 else "US"
    caption = f"Estimated: age blend · {st_label}×{idx:.2f}"
    return float(monthly), caption
