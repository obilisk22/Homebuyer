"""Tests for CA-aware maintenance blend resolver."""

from __future__ import annotations

from datetime import date

from app.core.home_maintenance import (
    ANGI_EMERGENCY_USD,
    ANGI_MAINTENANCE_USD,
    age_band_rates,
    resolve_monthly_maintenance,
    state_cost_index,
)


def test_state_index_california_is_1_15():
    assert state_cost_index("CA") == 1.15
    assert state_cost_index("ca") == 1.15


def test_state_index_unknown_defaults_to_1():
    assert state_cost_index("ZZ") == 1.0
    assert state_cost_index("") == 1.0
    assert state_cost_index(None) == 1.0


def test_age_band_under_10():
    year = date.today().year - 5
    pct, psf = age_band_rates(year)
    assert pct == 0.0075
    assert psf == 1.0


def test_age_band_40_plus():
    year = date.today().year - 50
    pct, psf = age_band_rates(year)
    assert pct == 0.015
    assert psf == 2.0


def test_age_band_unknown_uses_mid():
    pct, psf = age_band_rates(None)
    assert pct == 0.0125
    assert psf == 1.5


def test_resolve_returns_none_without_price_or_sqft():
    amt, src = resolve_monthly_maintenance(
        list_price=None,
        offer_price=None,
        sqft=None,
        year_built=1990,
        state="CA",
    )
    assert amt is None
    assert src == ""


def test_ca_estimate_higher_than_texas_same_home():
    kwargs = dict(
        list_price=800_000,
        offer_price=0,
        sqft=1800,
        year_built=date.today().year - 25,
    )
    ca_amt, ca_src = resolve_monthly_maintenance(**kwargs, state="CA")
    tx_amt, tx_src = resolve_monthly_maintenance(**kwargs, state="TX")
    assert ca_amt is not None and tx_amt is not None
    assert ca_amt > tx_amt
    assert "CA" in ca_src and "1.15" in ca_src
    assert "TX" in tx_src or "×" in tx_src


def test_blend_formula_matches_hand_calc_for_ca():
    """0.6 * reserve + 0.4 * observed, monthly rounded."""
    price = 600_000.0
    sqft = 2000.0
    # age 25 → 1.25% / $1.50
    year = date.today().year - 25
    idx = 1.15
    pct, psf = age_band_rates(year)
    reserve = ((pct * price) + (psf * sqft * idx)) / 2.0
    observed = (ANGI_MAINTENANCE_USD + ANGI_EMERGENCY_USD) * idx
    annual = 0.6 * reserve + 0.4 * observed
    expected = round(annual / 12.0)

    amt, src = resolve_monthly_maintenance(
        list_price=price,
        offer_price=0,
        sqft=sqft,
        year_built=year,
        state="CA",
    )
    assert amt == expected
    assert "age blend" in src.lower()


def test_no_sqft_uses_percent_leg_only():
    price = 500_000.0
    year = date.today().year - 5  # 0.75%
    idx = state_cost_index("ND")
    reserve = 0.0075 * price
    observed = (ANGI_MAINTENANCE_USD + ANGI_EMERGENCY_USD) * idx
    annual = 0.6 * reserve + 0.4 * observed
    expected = round(annual / 12.0)

    amt, _ = resolve_monthly_maintenance(
        list_price=price,
        offer_price=0,
        sqft=None,
        year_built=year,
        state="ND",
    )
    assert amt == expected


def test_no_price_uses_indexed_psf_only():
    sqft = 1500.0
    year = date.today().year - 5  # $1/sqft
    idx = 1.15
    reserve = 1.0 * sqft * idx
    observed = (ANGI_MAINTENANCE_USD + ANGI_EMERGENCY_USD) * idx
    annual = 0.6 * reserve + 0.4 * observed
    expected = round(annual / 12.0)

    amt, _ = resolve_monthly_maintenance(
        list_price=0,
        offer_price=0,
        sqft=sqft,
        year_built=year,
        state="CA",
    )
    assert amt == expected


def test_offer_price_preferred_over_list():
    year = date.today().year - 5
    with_offer, _ = resolve_monthly_maintenance(
        list_price=1_000_000,
        offer_price=500_000,
        sqft=None,
        year_built=year,
        state="ND",
    )
    list_only, _ = resolve_monthly_maintenance(
        list_price=500_000,
        offer_price=0,
        sqft=None,
        year_built=year,
        state="ND",
    )
    assert with_offer == list_only
