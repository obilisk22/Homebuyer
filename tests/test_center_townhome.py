"""Tests for center-townhome chip + listing position scrape (TODO-052)."""

from __future__ import annotations

from types import SimpleNamespace

from app.core.listing_signals import center_townhome_chip, listing_risk_chips
from app.core.zillow_listing import (
    classify_townhome_position,
    extract_listing_details,
)


def test_classify_townhome_position_center_and_end():
    assert (
        classify_townhome_position(
            "Beautiful mid-row townhome with patio",
            home_type="Townhouse",
        )
        == "center"
    )
    assert (
        classify_townhome_position(
            "Rare end unit townhouse with extra windows",
            home_type="Townhouse",
        )
        == "end"
    )
    # Ambiguous / both → no chip signal
    assert (
        classify_townhome_position(
            "Interior unit near the end unit courtyard",
            home_type="Townhouse",
        )
        == ""
    )
    # Non-townhouse even with interior language
    assert (
        classify_townhome_position(
            "Interior unit condo with great light",
            home_type="Condo",
        )
        == ""
    )
    assert classify_townhome_position("", home_type="Townhouse") == ""


def test_extract_listing_sets_townhome_position():
    html = (
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"componentProps":{"gdpClientCache":"'
        '{\\"zpid\\":9,\\"price\\":900000,\\"homeType\\":\\"TOWNHOUSE\\",'
        '\\"description\\":\\"Sunny middle unit townhome\\"}"'
        '}}}}'
        "</script>"
        "This middle unit has shared walls on both sides."
    )
    details = extract_listing_details(html)
    assert details.home_type == "Townhouse"
    assert details.townhome_position == "center"


def test_center_townhome_chip_only_when_clear():
    assert (
        center_townhome_chip(
            SimpleNamespace(home_type="Townhouse", townhome_position="end")
        )
        is None
    )
    assert (
        center_townhome_chip(
            SimpleNamespace(home_type="Condo", townhome_position="center")
        )
        is None
    )
    chip = center_townhome_chip(
        SimpleNamespace(home_type="Townhouse", townhome_position="center")
    )
    assert chip is not None
    assert chip["key"] == "center_townhome"
    assert chip["kind"] == "risk"
    assert "Mid-row" in chip["tooltip"] or "mid-row" in chip["tooltip"].casefold()

    chips = listing_risk_chips(
        SimpleNamespace(
            has_central_ac=True,
            cooling="Central Air",
            home_type="Townhouse",
            townhome_position="center",
        )
    )
    assert any(c["key"] == "center_townhome" for c in chips)
