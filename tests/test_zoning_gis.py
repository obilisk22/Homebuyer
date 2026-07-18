"""Unit tests for zoning helpers (no live ArcGIS required)."""

from __future__ import annotations

from app.core.zoning_gis import (
    FEEDS,
    ZONING_LEGEND,
    categorize_zone,
    normalize_zoning_feature,
    resolve_zoning_feed,
    zoning_supported,
)


def test_categorize_zone_residential_commercial():
    assert categorize_zone("R1-1") == "Residential"
    assert categorize_zone("RD1.5-1") == "Residential"
    assert categorize_zone("C2-1VL") == "Commercial"
    assert categorize_zone("M2-1", "Light Manufacturing") == "Industrial"
    assert categorize_zone("OS-1XL", "Open Space") == "Open / Public"
    assert categorize_zone("NV") == "Mixed / Other"


def test_resolve_santa_monica_and_la():
    assert resolve_zoning_feed("Santa Monica", 34.02, -118.49) is FEEDS["santa_monica"]
    assert resolve_zoning_feed("Los Angeles", 34.05, -118.25) is FEEDS["la_city"]
    assert resolve_zoning_feed("LA", 34.05, -118.25) is FEEDS["la_city"]
    assert resolve_zoning_feed("Torrance", 33.84, -118.34) is FEEDS["la_county"]
    assert resolve_zoning_feed("Portland", 45.5, -122.6) is None
    assert zoning_supported("Santa Monica", 34.02, -118.49)
    assert not zoning_supported("Austin", 30.27, -97.74)


def test_resolve_sm_bbox_without_city():
    assert resolve_zoning_feed("", 34.019, -118.491) is FEEDS["santa_monica"]


def test_normalize_zoning_feature_popup():
    feat = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
        },
        "properties": {"ZONE_CMPLT": "R1-1", "ZONE_CLASS": "Residential"},
    }
    norm = normalize_zoning_feature(feat, FEEDS["la_city"])
    assert norm is not None
    assert norm["properties"]["zone_code"] == "R1-1"
    assert norm["properties"]["category"] == "Residential"
    assert norm["properties"]["fillColor"] == "#00E5FF"
    assert "R1-1" in norm["properties"]["popup"]
    assert "ZIMAS" in norm["properties"]["popup"]


def test_zoning_legend_has_categories():
    labels = [label for label, _ in ZONING_LEGEND]
    assert "Residential" in labels
    assert "Commercial" in labels
