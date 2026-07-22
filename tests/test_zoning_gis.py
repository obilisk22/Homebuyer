"""Unit tests for zoning helpers (no live ArcGIS required)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core import zoning_gis
from app.core.cache import memo_clear, read_json
from app.core.zoning_gis import (
    CACHE_REV,
    DEFAULT_HALF_SPAN_DEG,
    FEEDS,
    ZONING_LEGEND,
    bbox_around,
    categorize_zone,
    normalize_zoning_feature,
    resolve_zoning_feed,
    zoning_supported,
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


def test_resolve_la_city_name_beats_sm_bbox():
    """Mar Vista sits near SM but is City of LA — do not steal the feed."""
    assert resolve_zoning_feed("Los Angeles", 34.021, -118.456) is FEEDS["la_city"]
    assert resolve_zoning_feed("LA", 34.021, -118.456) is FEEDS["la_city"]


def test_resolve_mar_vista_empty_city_uses_la_not_sm():
    """Empty city + Mar Vista must not hit the loose SM bbox (SCAG CITY=SM pockets)."""
    assert resolve_zoning_feed("", 34.021, -118.456) is FEEDS["la_city"]


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


def test_normalize_zoning_feature_strips_raw_fields():
    """Slim props only — raw ArcGIS fields bloat the NiceGUI WS payload."""
    feat = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
        },
        "properties": {
            "ZONE_CMPLT": "R1-1",
            "ZONE_CLASS": "Residential",
            "ZONELEGEND": "R1",
        },
    }
    norm = normalize_zoning_feature(feat, FEEDS["la_city"])
    assert norm is not None
    props = norm["properties"]
    assert "ZONE_CMPLT" not in props
    assert "ZONE_CLASS" not in props
    assert "ZONELEGEND" not in props
    assert set(props.keys()) == {"zone_code", "category", "fillColor", "source", "popup"}


def test_zoning_legend_has_categories():
    labels = [label for label, _ in ZONING_LEGEND]
    assert "Residential" in labels
    assert "Commercial" in labels


def test_la_city_uses_citywide_zoning_not_chapter_1a_only():
    """Root cause of pocket coverage: layer 1101 is Chapter 1A rollout only.

    Westside / Hollywood pins often return 0 features on 1101 while 1102
    (citywide Zoning) fills the same bbox continuously.
    """
    url = FEEDS["la_city"].query_url
    assert "/1102/" in url
    assert "/1101/" not in url


def test_default_half_span_covers_typical_map_viewport():
    """0.012° (~0.8 mi half) left most of the map empty; match ACS-scale bbox."""
    assert DEFAULT_HALF_SPAN_DEG >= 0.035
    min_lng, min_lat, max_lng, max_lat = bbox_around(34.02, -118.45)
    assert pytest.approx(max_lng - min_lng, rel=1e-6) == 2 * DEFAULT_HALF_SPAN_DEG
    assert pytest.approx(max_lat - min_lat, rel=1e-6) == 2 * DEFAULT_HALF_SPAN_DEG


def test_query_arcgis_paginates_until_complete(monkeypatch):
    """ArcGIS maxRecordCount truncates; pockets appear if we stop at page 1."""
    calls: list[dict] = []

    def fake_get(url, params=None, headers=None, timeout=None):  # noqa: ARG001
        offset = int((params or {}).get("resultOffset") or 0)
        calls.append(dict(params or {}))
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if offset == 0:
            resp.json.return_value = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                        "properties": {"ZONE_CMPLT": "R1-1", "ZONE_CLASS": "Residential"},
                    }
                ],
                "exceededTransferLimit": True,
            }
        else:
            resp.json.return_value = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": [[[1, 1], [2, 1], [2, 2], [1, 1]]]},
                        "properties": {"ZONE_CMPLT": "C2-1", "ZONE_CLASS": "Commercial"},
                    }
                ],
                "exceededTransferLimit": False,
            }
        return resp

    monkeypatch.setattr(zoning_gis.requests, "get", fake_get)
    payload = zoning_gis._query_arcgis_geojson(
        FEEDS["la_city"], (-118.5, 34.0, -118.4, 34.1)
    )
    assert len(payload["features"]) == 2
    assert len(calls) == 2
    assert calls[0].get("resultOffset") in (None, "0", 0)
    assert str(calls[1].get("resultOffset")) == "1"
    assert "maxAllowableOffset" not in calls[0]
    assert "geometryPrecision" not in calls[0]


def test_query_near_pin_shrinks_when_truncated(monkeypatch):
    """Dense SM bbox hits MAX_FEATURES; pick largest complete span under the cap."""
    spans_seen: list[float] = []

    def fake_query(feed, bbox):  # noqa: ARG001
        half = (bbox[2] - bbox[0]) / 2
        spans_seen.append(half)
        truncated = half > 0.015
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
                    },
                    "properties": {
                        "ZN24_CITY": "R1",
                        "ZN24_SCAG": "Residential",
                        "CITY": "Santa Monica",
                    },
                }
            ],
            "exceededTransferLimit": truncated,
        }

    monkeypatch.setattr(zoning_gis, "_query_arcgis_geojson", fake_query)
    features, truncated, used_span, _bbox = zoning_gis._query_zoning_near_pin(
        FEEDS["santa_monica"], 34.009, -118.482, half_span_deg=0.04
    )
    assert features
    assert not truncated
    assert used_span < 0.04
    # Binary search should land near the 0.015 completeness threshold (not jump to MIN).
    assert used_span >= 0.012
    assert used_span <= 0.015 + 1e-9
    assert any(s >= 0.039 for s in spans_seen)


def test_zoning_result_is_quantized(monkeypatch):
    """build_zoning_geojson writes quantized coords at precision 5."""
    assert CACHE_REV == "v7"

    hi_prec = [
        [
            [-118.123456789, 34.123456789],
            [-118.123456780, 34.123456780],
            [-118.120000111, 34.120000111],
            [-118.123456789, 34.123456789],
        ]
    ]

    def fake_query(feed, lat, lng, *, half_span_deg):  # noqa: ARG001
        return (
            [
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": hi_prec},
                    "properties": {
                        "zone_code": "R1-1",
                        "category": "Residential",
                        "fillColor": "#00E5FF",
                        "source": feed.label,
                        "popup": "R1-1",
                    },
                }
            ],
            False,
            half_span_deg,
            (-118.5, 34.0, -118.4, 34.1),
        )

    monkeypatch.setattr(zoning_gis, "_query_zoning_near_pin", fake_query)
    result = zoning_gis.build_zoning_geojson("Los Angeles", 34.05, -118.25)
    ring = result["features"][0]["geometry"]["coordinates"][0]
    assert ring[0] == [-118.12346, 34.12346]
    assert all(len(str(pt[0]).split(".")[-1]) <= 5 for pt in ring if isinstance(pt[0], float))

    # Disk payload is also quantized (CACHE_REV bump).
    from app.core.overlay_cache import cache_key

    key = cache_key(
        "zoning",
        "la_city",
        f"{34.05:.3f}",
        f"{-118.25:.3f}",
        f"{DEFAULT_HALF_SPAN_DEG:.3f}",
        CACHE_REV,
    )
    cached = read_json("zoning", key, max_age_s=zoning_gis.CACHE_MAX_AGE_S)
    assert cached is not None
    cached_ring = cached["features"][0]["geometry"]["coordinates"][0]
    assert cached_ring[0] == [-118.12346, 34.12346]


def test_zoning_quantize_fallback_on_failure(monkeypatch):
    """If quantize raises, return the pre-quantize FeatureCollection."""
    hi_prec = [
        [
            [-118.123456789, 34.123456789],
            [-118.12, 34.12],
            [-118.11, 34.11],
            [-118.123456789, 34.123456789],
        ]
    ]

    def fake_query(feed, lat, lng, *, half_span_deg):  # noqa: ARG001
        return (
            [
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": hi_prec},
                    "properties": {
                        "zone_code": "R1-1",
                        "category": "Residential",
                        "fillColor": "#00E5FF",
                        "source": feed.label,
                        "popup": "R1-1",
                    },
                }
            ],
            False,
            half_span_deg,
            (-118.5, 34.0, -118.4, 34.1),
        )

    monkeypatch.setattr(zoning_gis, "_query_zoning_near_pin", fake_query)
    monkeypatch.setattr(
        zoning_gis,
        "quantize_geojson",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("bad geom")),
    )
    result = zoning_gis.build_zoning_geojson("Los Angeles", 34.05, -118.25)
    ring = result["features"][0]["geometry"]["coordinates"][0]
    assert ring[0] == [-118.123456789, 34.123456789]

