"""Tests for Redfin ZIP Active-market chip (TODO-051)."""

from __future__ import annotations

import json
from unittest.mock import patch

from app.core import market_activity as ma
from app.core.redfin_sales import (
    homes_sold_p75,
    parse_redfin_zip_rows,
    percentile_nearest_rank,
)


def test_parse_redfin_keeps_homes_sold():
    rows = [
        {
            "region": "Zip Code: 90066",
            "property_type": "All Residential",
            "period_duration": "30",
            "period_end": "2025-06-30",
            "median_sale_price": "1,150,000",
            "homes_sold": "28",
            "inventory": "40",
            "months_of_supply": "1.4",
            "state_code": "CA",
        },
        {
            "region": "Zip Code: 90066",
            "property_type": "All Residential",
            "period_duration": "30",
            "period_end": "2025-05-31",
            "median_sale_price": "1,100,000",
            "homes_sold": "10",
            "state_code": "CA",
        },
    ]
    best = parse_redfin_zip_rows(rows)
    assert best["90066"]["homes_sold"] == 28
    assert best["90066"]["inventory"] == 40
    assert best["90066"]["period_end"] == "2025-06-30"


def test_homes_sold_p75_and_threshold():
    assert percentile_nearest_rank([1, 2, 3, 4], 75) == 3.0
    zips = {
        "1": {"homes_sold": 4},
        "2": {"homes_sold": 8},
        "3": {"homes_sold": 12},
        "4": {"homes_sold": 20},
    }
    p75 = homes_sold_p75(zips)
    assert p75 == 12.0
    assert ma.active_threshold(p75) == max(ma.ACTIVE_HOMES_SOLD_FLOOR, 12)
    assert ma.is_active_market(20, p75=p75) is True
    assert ma.is_active_market(5, p75=p75) is False
    # Floor still applies when P75 is tiny.
    assert ma.active_threshold(3.0) == ma.ACTIVE_HOMES_SOLD_FLOOR
    assert ma.is_active_market(11, p75=3.0) is False
    assert ma.is_active_market(12, p75=3.0) is True


def test_chip_spec_only_when_active():
    quiet = {
        "zip_code": "90066",
        "supported": True,
        "active": False,
        "homes_sold": 5,
        "period_end": "2025-06-30",
        "p75_homes_sold": 12.0,
        "threshold": 12,
        "median_sale_price": 1_000_000.0,
        "error": "",
    }
    assert ma.chip_spec_for(quiet) is None

    hot = dict(quiet)
    hot["active"] = True
    hot["homes_sold"] = 28
    chip = ma.chip_spec_for(hot)
    assert chip is not None
    assert chip["key"] == "active_market"
    assert chip["tone"] == "amenity"
    assert "28 sales" in chip["tooltip"]
    assert "90066" in chip["tooltip"]


def test_compute_market_activity_uses_bundle(monkeypatch):
    bundle = {
        "zips": {
            "90210": {
                "median_sale_price": 2_000_000.0,
                "period_end": "2025-06-30",
                "homes_sold": 30,
            }
        },
        "homes_sold_p75": 15.0,
    }
    with patch.object(ma, "load_zip_market_bundle", return_value=bundle):
        act = ma.compute_market_activity("90210")
    assert act["supported"] is True
    assert act["active"] is True
    assert act["homes_sold"] == 30
    assert act["threshold"] == 15

    with patch.object(ma, "load_zip_market_bundle", return_value=bundle):
        missing = ma.compute_market_activity("00000")
    assert missing["supported"] is False
    assert missing["active"] is False


def test_parse_activity_json_roundtrip():
    raw = json.dumps(
        {
            "zip_code": "98101",
            "supported": True,
            "active": True,
            "homes_sold": 22,
            "period_end": "2025-06-30",
            "p75_homes_sold": 14.0,
            "threshold": 14,
            "median_sale_price": 800000.0,
            "error": "",
        }
    )
    parsed = ma.parse_activity_json(raw)
    assert parsed["homes_sold"] == 22
    assert parsed["active"] is True
    assert ma.parse_activity_json("")["supported"] is False
    assert ma.parse_activity_json("nope")["error"] == "bad_json"
