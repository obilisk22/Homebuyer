"""Unit tests for schools / wildfire / AQI / Redfin overlay helpers (no live net)."""

from __future__ import annotations

import pytest

from app.core.air_quality import (
    aqi_category,
    aqi_fill_color,
    parse_open_meteo_batch,
    parse_open_meteo_current,
)
from app.core.redfin_sales import parse_redfin_zip_rows, parse_zip_from_region
from app.core.schools_nces import (
    haversine_miles,
    miles_to_half_span_deg,
    normalize_level,
    parse_nces_features,
    schools_to_geojson,
)
from app.core.wildfire_whp import USFS_WHP_WMS_URL, wildfire_wms_layer_args


def test_haversine_and_radius_span():
    # ~69 miles per degree lat near equator-ish; LA-scale check.
    d = haversine_miles(34.05, -118.25, 34.05, -118.25)
    assert d == pytest.approx(0.0)
    near = haversine_miles(34.05, -118.25, 34.06, -118.25)
    assert 0.6 < near < 0.8
    half = miles_to_half_span_deg(4.0, 34.0)
    assert 0.05 < half < 0.1


def test_normalize_level():
    assert normalize_level(1) == "Elementary"
    assert normalize_level(2) == "Middle"
    assert normalize_level(3) == "High"
    assert normalize_level("High School") == "High"
    assert normalize_level("MIDDLE") == "Middle"
    assert normalize_level(None) == "Other"


def test_parse_nces_features_filters_by_radius():
    payload = {
        "features": [
            {
                "attributes": {
                    "NAME": "Near Elem",
                    "LEVEL": 1,
                    "NCESSCH": "060000000001",
                    "LEAID": "060001",
                    "LAT": 34.05,
                    "LON": -118.25,
                },
                "geometry": {"x": -118.25, "y": 34.05},
            },
            {
                "attributes": {
                    "NAME": "Far High",
                    "LEVEL": "High",
                    "NCESSCH": "060000000002",
                    "LAT": 35.0,
                    "LON": -118.25,
                },
                "geometry": {"x": -118.25, "y": 35.0},
            },
        ]
    }
    schools = parse_nces_features(
        payload, pin_lat=34.05, pin_lng=-118.25, radius_mi=4.0
    )
    assert len(schools) == 1
    assert schools[0]["name"] == "Near Elem"
    assert schools[0]["level"] == "Elementary"
    assert schools[0]["distance_mi"] == pytest.approx(0.0)

    geo = schools_to_geojson(schools)
    assert geo["type"] == "FeatureCollection"
    assert len(geo["features"]) == 1
    assert geo["features"][0]["geometry"]["type"] == "Point"


def test_parse_nces_features_ccd_field_aliases():
    payload = {
        "features": [
            {
                "attributes": {
                    "SCH_NAME": "CCD High",
                    "SLEVEL_TEXT": "High",
                    "NCESSCH": "060000000099",
                    "ST_LEAID": "CA-999",
                    "LATCOD": 34.05,
                    "LONCOD": -118.25,
                    "LCITY": "Los Angeles",
                },
                "geometry": {"x": -118.25, "y": 34.05},
            }
        ]
    }
    schools = parse_nces_features(
        payload, pin_lat=34.05, pin_lng=-118.25, radius_mi=4.0
    )
    assert len(schools) == 1
    assert schools[0]["name"] == "CCD High"
    assert schools[0]["level"] == "High"
    assert schools[0]["district"] == "CA-999"
    assert schools[0]["city"] == "Los Angeles"


def test_wildfire_wms_args():
    url, opts = wildfire_wms_layer_args()
    assert url == USFS_WHP_WMS_URL
    assert opts["layers"] == "0"
    assert opts["transparent"] is True


def test_aqi_color_and_parse():
    assert aqi_fill_color(None) == "#2A3340"
    assert aqi_fill_color(40) == "#00E5FF"
    assert aqi_fill_color(120) == "#FFC107"
    assert aqi_category(40) == "Good"
    assert aqi_category(250) == "Very unhealthy"

    assert parse_open_meteo_current({"current": {"us_aqi": 72}}) == 72.0
    assert parse_open_meteo_current({"current": {"us_aqi": None}}) is None

    batch = parse_open_meteo_batch(
        [
            {"latitude": 34.0, "longitude": -118.2, "current": {"us_aqi": 55}},
            {"latitude": 34.02, "longitude": -118.22, "current": {"us_aqi": 80}},
        ],
        [(34.0, -118.2), (34.02, -118.22)],
    )
    assert len(batch) == 2
    assert batch[0]["aqi"] == 55.0


def test_redfin_zip_parse_and_newest_period():
    assert parse_zip_from_region("Zip Code: 90066") == "90066"
    assert parse_zip_from_region("90210") == "90210"
    assert parse_zip_from_region("nope") is None

    rows = [
        {
            "region": "Zip Code: 90066",
            "property_type": "All Residential",
            "period_duration": "30",
            "period_end": "2024-01-31",
            "median_sale_price": "900000",
            "state_code": "CA",
        },
        {
            "region": "Zip Code: 90066",
            "property_type": "All Residential",
            "period_duration": "30",
            "period_end": "2025-06-30",
            "median_sale_price": "1,150,000",
            "state_code": "CA",
        },
        {
            "region": "Zip Code: 90066",
            "property_type": "Condo/Co-op",
            "period_duration": "30",
            "period_end": "2025-06-30",
            "median_sale_price": "500000",
            "state_code": "CA",
        },
        {
            "region": "Zip Code: 99999",
            "property_type": "All Residential",
            "period_duration": "90",
            "period_end": "2025-06-30",
            "median_sale_price": "100",
            "state_code": "CA",
        },
    ]
    best = parse_redfin_zip_rows(rows)
    assert best["90066"]["median_sale_price"] == 1_150_000.0
    assert best["90066"]["period_end"] == "2025-06-30"
    assert "99999" not in best
