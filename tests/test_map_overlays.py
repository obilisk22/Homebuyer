"""Unit tests for map overlay helpers (no live API required)."""

from __future__ import annotations

import pytest

from app.core.census_acs import (
    bbox_around,
    income_fill_color,
    parse_acs_tract_rows,
)
from app.core.crime_socrata import (
    CRIME_CITIES,
    crime_supported,
    normalize_city,
    resolve_crime_city,
    soda_where_preview,
)
from app.core.fema_flood import FEMA_NFHL_WMS_URL, flood_wms_layer_args


def test_bbox_around_symmetric():
    min_lng, min_lat, max_lng, max_lat = bbox_around(34.0, -118.4, 0.05)
    assert min_lat == pytest.approx(33.95)
    assert max_lat == pytest.approx(34.05)
    assert min_lng == pytest.approx(-118.45)
    assert max_lng == pytest.approx(-118.35)


def test_parse_acs_tract_rows():
    rows = [
        ["NAME", "B19013_001E", "state", "county", "tract"],
        ["Tract 1", "75000", "06", "037", "123456"],
        ["Tract 2", "-666666666", "06", "037", "123457"],
        ["Tract 3", "", "06", "037", "123458"],
    ]
    parsed = parse_acs_tract_rows(rows)
    assert parsed["06037123456"] == 75000.0
    assert parsed["06037123457"] is None
    assert parsed["06037123458"] is None


def test_income_fill_color_breaks():
    assert income_fill_color(None) == "#2A3340"
    assert income_fill_color(30_000) == "#1a237e"
    assert income_fill_color(90_000) == "#00E5FF"
    assert income_fill_color(200_000) == "#FF2BD6"


def test_crime_city_resolution():
    assert resolve_crime_city("Los Angeles") is CRIME_CITIES["los_angeles"]
    assert resolve_crime_city("LA") is CRIME_CITIES["los_angeles"]
    assert resolve_crime_city("Seattle") is CRIME_CITIES["seattle"]
    # Santa Monica / Pasadena / empty Westside pin → LA County (primary = LAPD).
    assert resolve_crime_city("Santa Monica") is CRIME_CITIES["los_angeles"]
    assert resolve_crime_city("Pasadena") is CRIME_CITIES["los_angeles"]
    assert resolve_crime_city("Torrance") is CRIME_CITIES["los_angeles"]
    assert resolve_crime_city("Portland") is None
    assert (
        resolve_crime_city("", 33.9916647, -118.4341763) is CRIME_CITIES["los_angeles"]
    )
    # Antelope Valley still in county bbox.
    assert resolve_crime_city("", 34.69, -118.15) is CRIME_CITIES["los_angeles"]
    assert crime_supported("seattle")
    assert crime_supported("Santa Monica")
    assert crime_supported("Long Beach")
    assert crime_supported("", 33.99, -118.43)
    assert not crime_supported("Austin")
    assert normalize_city("  Los   Angeles ") == "los angeles"

    from app.core.crime_socrata import resolve_crime_feeds

    feeds = resolve_crime_feeds("Santa Monica", 34.01, -118.49)
    assert [f.id for f in feeds] == ["los_angeles", "santa_monica"]


def test_soda_where_preview_contains_bbox_fields():
    la = CRIME_CITIES["los_angeles"]
    clause = soda_where_preview(la, 34.05, -118.25)
    assert "lat between" in clause
    assert "lon between" in clause
    sea = CRIME_CITIES["seattle"]
    assert "client-side" in soda_where_preview(sea, 47.6, -122.3)
    sm = CRIME_CITIES["santa_monica"]
    assert "ckan SQL bbox" in soda_where_preview(sm, 34.01, -118.49)

def test_fema_wms_args():
    url, options = flood_wms_layer_args()
    assert url == FEMA_NFHL_WMS_URL
    assert options["layers"] == "28"
    assert options["transparent"] is True
    assert "FEMA" in options["attribution"]
