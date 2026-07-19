"""Tests for utility provider resolution and monthly estimates."""

from app.core.utilities import (
    age_efficiency_factor,
    resolve_monthly_utilities,
    resolve_utility_providers,
)


def test_ladwp_for_los_angeles_city():
    elec, gas, la = resolve_utility_providers(
        city="Los Angeles", state="CA", zip_code="90026"
    )
    assert elec == "ladwp"
    assert gas == "socalgas"
    assert la is True


def test_sce_for_santa_monica():
    elec, gas, la = resolve_utility_providers(
        city="Santa Monica", state="CA", zip_code="90401"
    )
    assert elec == "sce"
    assert gas == "socalgas"
    assert la is True


def test_default_outside_socal():
    elec, gas, la = resolve_utility_providers(
        city="Seattle", state="WA", zip_code="98101"
    )
    assert elec == "default"
    assert gas == "default"
    assert la is False


def test_age_factor_increases_with_age():
    assert age_efficiency_factor(2024) < age_efficiency_factor(1990)
    assert age_efficiency_factor(1990) < age_efficiency_factor(1960)


def test_resolve_monthly_utilities_ladwp_positive():
    amt, src = resolve_monthly_utilities(
        sqft=2000,
        year_built=1985,
        city="Los Angeles",
        state="CA",
        zip_code="90026",
    )
    assert amt is not None and amt > 100
    assert "LADWP" in src
    assert "SoCalGas" in src


def test_resolve_monthly_utilities_assumes_sqft_when_missing():
    amt, src = resolve_monthly_utilities(
        sqft=None,
        year_built=2000,
        city="Seattle",
        state="WA",
        zip_code="98101",
    )
    assert amt is not None and amt > 0
    assert "sqft" in src.lower() or "~" in src


def test_larger_home_costs_more():
    small, _ = resolve_monthly_utilities(
        sqft=1000, year_built=2000, city="Los Angeles", state="CA", zip_code="90026"
    )
    large, _ = resolve_monthly_utilities(
        sqft=3000, year_built=2000, city="Los Angeles", state="CA", zip_code="90026"
    )
    assert small is not None and large is not None
    assert large > small
