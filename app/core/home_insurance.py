"""Resolve annual homeowners insurance from listing or state premium table."""

from __future__ import annotations

import json
from functools import lru_cache

from app.core.paths import package_data_file

_TABLE_PATH = package_data_file("home_insurance_rates.json")


@lru_cache(maxsize=1)
def _load_table() -> dict:
    with _TABLE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def resolve_annual_insurance(
    *,
    annual_insurance: float | None,
    list_price: float | None,
    state: str | None,
) -> tuple[float | None, str]:
    if annual_insurance is not None and annual_insurance > 0:
        return float(annual_insurance), "Zillow"

    price = float(list_price or 0)
    if price <= 0:
        return None, ""

    st = (state or "").strip().upper()
    if len(st) != 2:
        return None, ""

    table = _load_table()
    premiums: dict = table.get("avg_premium_usd") or {}
    avg = premiums.get(st)
    if avg is None:
        return None, ""

    ref = float(table.get("reference_coverage_usd") or 300_000)
    if ref <= 0:
        return None, ""

    estimate = float(avg) * (price / ref)
    return round(estimate), f"Estimated: {st} avg premium"
