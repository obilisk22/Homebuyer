"""Estimate monthly utilities from provider territory, sqft, and home age."""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache

from app.core.paths import package_data_file

_TABLE_PATH = package_data_file("utility_providers.json")


@lru_cache(maxsize=1)
def _load_table() -> dict:
    with _TABLE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _norm_city(city: str | None) -> str:
    return " ".join((city or "").strip().lower().split())


def _zip5(zip_code: str | None) -> str:
    digits = "".join(ch for ch in (zip_code or "") if ch.isdigit())
    return digits[:5] if len(digits) >= 5 else digits


def _zip_prefix3(zip_code: str | None) -> str:
    z = _zip5(zip_code)
    return z[:3] if len(z) >= 3 else ""


def age_efficiency_factor(year_built: int | None) -> float:
    """Older stock tends to use more energy; unknown age → mild uplift."""
    table = _load_table()
    factors = table.get("age_factors") or {}
    if year_built is None:
        return float(factors.get("unknown") or 1.05)
    try:
        yb = int(year_built)
    except (TypeError, ValueError):
        return float(factors.get("unknown") or 1.05)
    if yb < 1800 or yb > date.today().year + 1:
        return float(factors.get("unknown") or 1.05)
    age = max(0, date.today().year - yb)
    if age < 10:
        return float(factors.get("under_10") or 0.85)
    if age < 20:
        return float(factors.get("under_20") or 1.0)
    if age < 40:
        return float(factors.get("under_40") or 1.15)
    return float(factors.get("40_plus") or 1.3)


def resolve_utility_providers(
    *,
    city: str | None = None,
    state: str | None = None,
    zip_code: str | None = None,
) -> tuple[str, str, bool]:
    """Return ``(electric_key, gas_key, is_la_area)``.

    LA-area heuristics: LADWP vs SCE for electric; SoCalGas for gas when in SoCal.
    Unknown → ``default`` / ``default``.
    """
    table = _load_table()
    city_n = _norm_city(city)
    st = (state or "").strip().upper()
    prefix = _zip_prefix3(zip_code)

    sce_cities = {_norm_city(c) for c in (table.get("sce_cities") or [])}
    ladwp_cities = {_norm_city(c) for c in (table.get("ladwp_cities") or [])}
    ladwp_prefixes = {str(p) for p in (table.get("ladwp_zip_prefixes") or [])}
    socal_prefixes = {str(p) for p in (table.get("socal_zip_prefixes") or [])}

    in_socal = st == "CA" and (
        prefix in socal_prefixes or city_n in sce_cities or city_n in ladwp_cities
    )
    # City of LA neighborhoods often listed as "Los Angeles"
    if city_n == "los angeles" or city_n in ladwp_cities or prefix in ladwp_prefixes:
        if city_n in sce_cities:
            return "sce", "socalgas", True
        return "ladwp", "socalgas", True
    if city_n in sce_cities or (st == "CA" and prefix in socal_prefixes):
        return "sce", "socalgas", True
    if in_socal:
        return "sce", "socalgas", True
    return "default", "default", False


def resolve_monthly_utilities(
    *,
    sqft: float | None,
    year_built: int | None = None,
    city: str | None = None,
    state: str | None = None,
    zip_code: str | None = None,
) -> tuple[float | None, str]:
    """Estimate total monthly utilities (electric + gas + water/trash).

    Returns ``(None, "")`` only when the table cannot be loaded; otherwise always
    returns a positive estimate (assumes mid-size home when sqft missing).
    """
    try:
        table = _load_table()
    except Exception:  # noqa: BLE001
        return None, ""

    electric_key, gas_key, la_area = resolve_utility_providers(
        city=city, state=state, zip_code=zip_code
    )
    electric = (table.get("electric") or {}).get(electric_key) or (
        table.get("electric") or {}
    ).get("default") or {}
    gas = (table.get("gas") or {}).get(gas_key) or (table.get("gas") or {}).get(
        "default"
    ) or {}
    water_map = table.get("water_trash_usd_mo") or {}
    water = float(
        water_map.get("la_area" if la_area else "default")
        or water_map.get("default")
        or 90
    )

    assumed = float(table.get("assumed_sqft_when_missing") or 1800)
    area = float(sqft or 0)
    used_assumed = area <= 0
    if used_assumed:
        area = assumed

    e_psf = float(electric.get("usd_per_sqft_mo") or 0.055)
    g_base = float(gas.get("base_usd_mo") or 18)
    g_psf = float(gas.get("usd_per_sqft_mo") or 0.012)
    age_f = age_efficiency_factor(year_built)

    energy = (e_psf * area + g_base + g_psf * area) * age_f
    monthly = round(energy + water)

    e_label = str(electric.get("label") or electric_key)
    g_label = str(gas.get("label") or gas_key)
    bits = [f"Estimated: {e_label}+{g_label}"]
    if used_assumed:
        bits.append(f"~{int(assumed)} sqft")
    bits.append(f"age×{age_f:.2f}")
    return float(monthly), " · ".join(bits)
