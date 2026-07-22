"""Unit tests for map overlay helpers (no live API required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.cache import memo_clear, memo_get
from app.core.census_acs import (
    AVG_KIDS_BREAKS,
    HOME_VALUE_BREAKS,
    INCOME_BREAKS,
    MEDIAN_AGE_BREAKS,
    bbox_around,
    fill_color_for_breaks,
    parse_acs_avg_kids_rows,
    parse_acs_tract_rows,
)


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEBUY_DATA_DIR", str(tmp_path))
    from app.core import paths

    monkeypatch.setattr(paths, "DATA_DIR", Path(tmp_path))
    paths.refresh_data_dirs()
    memo_clear()
    yield
    memo_clear()
from app.core.crime_socrata import (
    CRIME_CITIES,
    bbox_around as crime_bbox_around,
    crime_supported,
    normalize_city,
    resolve_crime_feeds,
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
    assert fill_color_for_breaks(None, INCOME_BREAKS) == "#2A3340"
    assert fill_color_for_breaks(30_000, INCOME_BREAKS) == "#1a237e"
    assert fill_color_for_breaks(90_000, INCOME_BREAKS) == "#00E5FF"
    assert fill_color_for_breaks(200_000, INCOME_BREAKS) == "#FF2BD6"


def test_home_value_and_age_fill_breaks():
    assert fill_color_for_breaks(350_000, HOME_VALUE_BREAKS) == "#1a237e"
    assert fill_color_for_breaks(900_000, HOME_VALUE_BREAKS) == "#00E5FF"
    assert fill_color_for_breaks(2_000_000, HOME_VALUE_BREAKS) == "#FF2BD6"
    assert fill_color_for_breaks(28, MEDIAN_AGE_BREAKS) == "#00838f"
    assert fill_color_for_breaks(42, MEDIAN_AGE_BREAKS) == "#B8FF3C"
    assert fill_color_for_breaks(55, MEDIAN_AGE_BREAKS) == "#FF2BD6"


def test_parse_acs_avg_kids_rows():
    rows = [
        ["NAME", "B09001_001E", "B25003_001E", "state", "county", "tract"],
        ["Tract A", "100", "200", "06", "037", "123456"],
        ["Tract B", "50", "0", "06", "037", "123457"],
        ["Tract C", "-666666666", "100", "06", "037", "123458"],
        ["Tract D", "0", "80", "06", "037", "123459"],
    ]
    parsed = parse_acs_avg_kids_rows(rows)
    assert parsed["06037123456"] == pytest.approx(0.5)
    assert parsed["06037123457"] is None
    assert parsed["06037123458"] is None
    assert parsed["06037123459"] == pytest.approx(0.0)
    assert fill_color_for_breaks(0.5, AVG_KIDS_BREAKS) == "#283593"


def test_parse_owner_occ_year_rent_bachelors():
    from app.core.census_acs import (
        BACHELORS_BREAKS,
        GROSS_RENT_BREAKS,
        OWNER_OCC_BREAKS,
        YEAR_BUILT_BREAKS,
        parse_acs_bachelors_pct_rows,
        parse_acs_gross_rent_rows,
        parse_acs_owner_occ_pct_rows,
        parse_acs_year_built_rows,
    )

    owner_rows = [
        ["NAME", "B25003_001E", "B25003_002E", "state", "county", "tract"],
        ["A", "100", "80", "06", "037", "111111"],
        ["B", "0", "10", "06", "037", "222222"],
    ]
    owners = parse_acs_owner_occ_pct_rows(owner_rows)
    assert owners["06037111111"] == pytest.approx(80.0)
    assert owners["06037222222"] is None
    assert fill_color_for_breaks(80, OWNER_OCC_BREAKS) == "#00E5FF"

    year_rows = [
        ["NAME", "B25035_001E", "state", "county", "tract"],
        ["A", "1974", "06", "037", "111111"],
        ["B", "-666666666", "06", "037", "222222"],
    ]
    years = parse_acs_year_built_rows(year_rows)
    assert years["06037111111"] == 1974.0
    assert years["06037222222"] is None
    assert fill_color_for_breaks(1974, YEAR_BUILT_BREAKS) == "#7b1fa2"

    rent_rows = [
        ["NAME", "B25064_001E", "state", "county", "tract"],
        ["A", "2750", "06", "037", "111111"],
    ]
    rents = parse_acs_gross_rent_rows(rent_rows)
    assert rents["06037111111"] == 2750.0
    assert fill_color_for_breaks(2750, GROSS_RENT_BREAKS) == "#00E5FF"

    edu_rows = [
        [
            "NAME",
            "B15003_001E",
            "B15003_022E",
            "B15003_023E",
            "B15003_024E",
            "B15003_025E",
            "state",
            "county",
            "tract",
        ],
        ["A", "100", "30", "10", "5", "5", "06", "037", "111111"],
    ]
    edu = parse_acs_bachelors_pct_rows(edu_rows)
    assert edu["06037111111"] == pytest.approx(50.0)
    assert fill_color_for_breaks(50, BACHELORS_BREAKS) == "#00E5FF"


def test_acs_layers_include_new_demos():
    from app.core.census_acs import ACS_LAYERS

    assert {
        "owner_occ",
        "year_built",
        "gross_rent",
        "bachelors",
    }.issubset(ACS_LAYERS)


def test_crime_city_resolution():
    def primary(city, lat=None, lng=None):
        feeds = resolve_crime_feeds(city, lat, lng)
        return feeds[0] if feeds else None

    assert primary("Los Angeles") is CRIME_CITIES["los_angeles"]
    assert primary("LA") is CRIME_CITIES["los_angeles"]
    assert primary("Seattle") is CRIME_CITIES["seattle"]
    # Santa Monica / Pasadena / empty Westside pin → LA County (primary = LAPD).
    assert primary("Santa Monica") is CRIME_CITIES["los_angeles"]
    assert primary("Pasadena") is CRIME_CITIES["los_angeles"]
    assert primary("Torrance") is CRIME_CITIES["los_angeles"]
    assert primary("Portland") is None
    assert primary("", 33.9916647, -118.4341763) is CRIME_CITIES["los_angeles"]
    # Antelope Valley still in county bbox.
    assert primary("", 34.69, -118.15) is CRIME_CITIES["los_angeles"]
    assert crime_supported("seattle")
    assert crime_supported("Santa Monica")
    assert crime_supported("Long Beach")
    assert crime_supported("", 33.99, -118.43)
    assert not crime_supported("Austin")
    assert normalize_city("  Los   Angeles ") == "los angeles"

    feeds = resolve_crime_feeds("Santa Monica", 34.01, -118.49)
    assert [f.id for f in feeds] == ["los_angeles", "santa_monica"]


def test_crime_feed_filter_fields():
    """Sanity-check per-feed lat/lng field names used by SODA / CKAN queries."""
    la = CRIME_CITIES["los_angeles"]
    assert la.lat_field == "lat"
    assert la.lng_field == "lon"
    assert la.coords_numeric is True
    sea = CRIME_CITIES["seattle"]
    assert sea.coords_numeric is False
    sm = CRIME_CITIES["santa_monica"]
    assert sm.kind == "ckan"
    min_lng, min_lat, max_lng, max_lat = crime_bbox_around(34.05, -118.25)
    assert min_lat < 34.05 < max_lat
    assert min_lng < -118.25 < max_lng

def test_fema_wms_args():
    url, options = flood_wms_layer_args()
    assert url == FEMA_NFHL_WMS_URL
    assert options["layers"] == "28"
    assert options["transparent"] is True
    assert "FEMA" in options["attribution"]


def test_acs_styled_geojson_is_quantized(monkeypatch):
    """Styled ACS FeatureCollection coords are quantized at precision 5 + memoized."""
    from app.core import census_acs as acs

    hi_prec = [
        [
            [-118.123456789, 34.123456789],
            [-118.123456780, 34.123456780],
            [-118.120000111, 34.120000111],
            [-118.123456789, 34.123456789],
        ]
    ]

    monkeypatch.setattr(acs, "_fcc_fips", lambda lat, lng: ("06", "037"))  # noqa: ARG005
    monkeypatch.setattr(
        acs,
        "_fetch_acs_values",
        lambda layer, state_fips, county_fips: {"06037123456": 90_000.0},  # noqa: ARG005
    )
    monkeypatch.setattr(
        acs,
        "_fetch_tract_geojson",
        lambda bbox, state_fips, county_fips: {  # noqa: ARG005
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": hi_prec},
                    "properties": {"GEOID": "06037123456", "NAME": "Tract 1"},
                }
            ],
        },
    )

    result = acs.build_acs_geojson("income", 34.05, -118.25)
    ring = result["features"][0]["geometry"]["coordinates"][0]
    assert ring[0] == [-118.12346, 34.12346]
    assert result["features"][0]["properties"]["fillColor"]
    assert result["meta"]["layer_id"] == "income"

    # Process memo hit on re-toggle (same layer + bbox key).
    second = acs.build_acs_geojson("income", 34.05, -118.25)
    assert second == result
    key = acs._styled_memo_key("income", 34.05, -118.25, acs.DEFAULT_HALF_SPAN_DEG)
    assert memo_get(acs.STYLED_MEMO_NS, key) is not None


def test_acs_quantize_fallback_on_failure(monkeypatch):
    from app.core import census_acs as acs

    hi_prec = [
        [
            [-118.123456789, 34.123456789],
            [-118.12, 34.12],
            [-118.11, 34.11],
            [-118.123456789, 34.123456789],
        ]
    ]

    monkeypatch.setattr(acs, "_fcc_fips", lambda lat, lng: ("06", "037"))  # noqa: ARG005
    monkeypatch.setattr(
        acs,
        "_fetch_acs_values",
        lambda layer, state_fips, county_fips: {"06037123456": 50_000.0},  # noqa: ARG005
    )
    monkeypatch.setattr(
        acs,
        "_fetch_tract_geojson",
        lambda bbox, state_fips, county_fips: {  # noqa: ARG005
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": hi_prec},
                    "properties": {"GEOID": "06037123456", "NAME": "Tract 1"},
                }
            ],
        },
    )
    monkeypatch.setattr(
        acs,
        "quantize_geojson",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("bad geom")),
    )
    result = acs.build_acs_geojson("income", 34.05, -118.25)
    ring = result["features"][0]["geometry"]["coordinates"][0]
    assert ring[0] == [-118.123456789, 34.123456789]
