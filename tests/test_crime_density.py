"""Unit tests for crime hex density choropleth (no live APIs)."""

from __future__ import annotations

from app.core.crime_density import (
    CRIME_LEGEND,
    HEX_SIZE_DEG,
    bin_points_to_hex,
    build_crime_density_geojson,
    crime_fill_color,
    hex_cell_polygon,
)


def test_crime_fill_color_breaks():
    assert crime_fill_color(1) == "#4A148C"
    assert crime_fill_color(2) == "#4A148C"
    assert crime_fill_color(3) == "#9C27B0"
    assert crime_fill_color(5) == "#9C27B0"
    assert crime_fill_color(6) == "#FF2BD6"
    assert crime_fill_color(10) == "#FF2BD6"
    assert crime_fill_color(11) == "#FF80AB"
    assert crime_fill_color(20) == "#FF80AB"
    assert crime_fill_color(21) == "#B8FF3C"
    assert crime_fill_color(100) == "#B8FF3C"


def test_crime_legend_matches_palette():
    labels = [label for label, _ in CRIME_LEGEND]
    colors = [color for _, color in CRIME_LEGEND]
    assert "1–2" in labels[0] or "1-2" in labels[0]
    assert "#4A148C" in colors
    assert "#B8FF3C" in colors


def test_empty_points_yield_empty_geojson():
    geo = build_crime_density_geojson([])
    assert geo["type"] == "FeatureCollection"
    assert geo["features"] == []
    assert geo["meta"]["incidents"] == 0
    assert geo["meta"]["cells"] == 0


def test_invalid_points_skipped():
    geo = build_crime_density_geojson(
        [
            {"lat": "x", "lng": -118.4},
            {"lat": 34.0},  # missing lng
            {"lat": None, "lng": None},
        ]
    )
    assert geo["features"] == []
    assert geo["meta"]["incidents"] == 0


def test_cluster_in_one_cell():
    # Identical / nearly identical coords → one hex cell
    base_lat, base_lng = 34.0100, -118.4900
    pts = [
        {"lat": base_lat, "lng": base_lng},
        {"lat": base_lat, "lng": base_lng},
        {"lat": base_lat + 1e-7, "lng": base_lng + 1e-7},
    ]
    geo = build_crime_density_geojson(pts)
    assert geo["meta"]["incidents"] == 3
    assert geo["meta"]["cells"] == 1
    assert len(geo["features"]) == 1
    feat = geo["features"][0]
    assert feat["properties"]["count"] == 3
    assert feat["properties"]["fillColor"] == crime_fill_color(3)
    assert "3" in feat["properties"]["popup"]


def test_spread_points_multiple_cells_sum_counts():
    size = HEX_SIZE_DEG
    pts = [
        {"lat": 34.0, "lng": -118.5},
        {"lat": 34.0 + size * 3, "lng": -118.5},
        {"lat": 34.0, "lng": -118.5 + size * 3},
        {"lat": 34.0 + size * 3, "lng": -118.5 + size * 3},
    ]
    geo = build_crime_density_geojson(pts)
    assert geo["meta"]["incidents"] == 4
    assert geo["meta"]["cells"] >= 2
    total = sum(f["properties"]["count"] for f in geo["features"])
    assert total == 4


def test_hex_polygon_closed_lng_lat_order():
    ring = hex_cell_polygon(0, 0, HEX_SIZE_DEG)
    assert len(ring) == 7  # 6 corners + close
    assert ring[0] == ring[-1]
    for lng, lat in ring:
        assert isinstance(lng, float)
        assert isinstance(lat, float)


def test_bin_points_to_hex_counts():
    pts = [
        {"lat": 34.0, "lng": -118.5},
        {"lat": 34.0, "lng": -118.5},
    ]
    bins = bin_points_to_hex(pts, size_deg=HEX_SIZE_DEG)
    assert sum(bins.values()) == 2
    assert all(isinstance(k, tuple) and len(k) == 2 for k in bins)


def test_geojson_days_in_meta():
    geo = build_crime_density_geojson([{"lat": 34.0, "lng": -118.5}], days=180)
    assert geo["meta"]["days"] == 180
