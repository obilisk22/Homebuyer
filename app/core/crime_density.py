"""Hex-bin crime density choropleth helpers (no network).

Approximates axial hexes in degree space for neighborhood-scale bboxes —
not equal-area globe projection, good enough for Map overlays near a pin.
"""

from __future__ import annotations

import math
from typing import Any

# ~400m at mid-latitudes; readable at Leaflet zoom ~14.
HEX_SIZE_DEG = 0.004

# Count breaks → fill colors (cyberpunk purple → magenta → lime hot-spot).
CRIME_BREAKS: list[tuple[int, str]] = [
    (2, "#4A148C"),
    (5, "#9C27B0"),
    (10, "#FF2BD6"),
    (20, "#FF80AB"),
    (10**9, "#B8FF3C"),
]

CRIME_LEGEND: list[tuple[str, str]] = [
    ("1–2", "#4A148C"),
    ("3–5", "#9C27B0"),
    ("6–10", "#FF2BD6"),
    ("11–20", "#FF80AB"),
    ("21+", "#B8FF3C"),
]

DEFAULT_DAYS = 365


def crime_fill_color(count: int) -> str:
    if count <= 0:
        return "#2A3340"
    for threshold, color in CRIME_BREAKS:
        if count <= threshold:
            return color
    return CRIME_BREAKS[-1][1]


def _axial_from_lng_lat(lng: float, lat: float, size_deg: float) -> tuple[int, int]:
    """Pointy-top axial (q, r) from lng/lat using size as hex 'size' in degrees."""
    # https://www.redblobgames.com/grids/hexagons/#pixel-to-hex (pointy)
    x = lng / size_deg
    y = lat / size_deg
    q = (math.sqrt(3) / 3 * x - 1.0 / 3.0 * y)
    r = (2.0 / 3.0 * y)
    return _axial_round(q, r)


def _axial_round(q: float, r: float) -> tuple[int, int]:
    s = -q - r
    rq = round(q)
    rr = round(r)
    rs = round(s)
    q_diff = abs(rq - q)
    r_diff = abs(rr - r)
    s_diff = abs(rs - s)
    if q_diff > r_diff and q_diff > s_diff:
        rq = -rr - rs
    elif r_diff > s_diff:
        rr = -rq - rs
    return int(rq), int(rr)


def hex_cell_polygon(q: int, r: int, size_deg: float) -> list[list[float]]:
    """Exterior ring of pointy-top hex as [lng, lat] pairs (closed)."""
    # Center in "pixel" space then to lng/lat degrees
    cx = size_deg * (math.sqrt(3) * q + math.sqrt(3) / 2 * r)
    cy = size_deg * (3.0 / 2.0 * r)
    ring: list[list[float]] = []
    for i in range(6):
        angle = math.radians(60 * i - 30)  # pointy-top
        ring.append([cx + size_deg * math.cos(angle), cy + size_deg * math.sin(angle)])
    ring.append(ring[0][:])
    return ring


def bin_points_to_hex(
    points: list[dict[str, Any]],
    *,
    size_deg: float = HEX_SIZE_DEG,
) -> dict[tuple[int, int], int]:
    bins: dict[tuple[int, int], int] = {}
    for pt in points:
        try:
            lat = float(pt["lat"])
            lng = float(pt["lng"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(lat) or not math.isfinite(lng):
            continue
        key = _axial_from_lng_lat(lng, lat, size_deg)
        bins[key] = bins.get(key, 0) + 1
    return bins


def build_crime_density_geojson(
    points: list[dict[str, Any]],
    *,
    size_deg: float = HEX_SIZE_DEG,
    days: int = DEFAULT_DAYS,
    half_span_deg: float | None = None,  # reserved; binning uses all valid points
) -> dict[str, Any]:
    """Build a FeatureCollection of hex polygons colored by incident count."""
    _ = half_span_deg  # API compatibility with design / callers
    bins = bin_points_to_hex(points, size_deg=size_deg)
    features: list[dict[str, Any]] = []
    incidents = 0
    for (q, r), count in bins.items():
        if count <= 0:
            continue
        incidents += count
        color = crime_fill_color(count)
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "count": count,
                    "fillColor": color,
                    "popup": f"{count} incident{'s' if count != 1 else ''} (last {days} days)",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [hex_cell_polygon(q, r, size_deg)],
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "incidents": incidents,
            "cells": len(features),
            "days": days,
        },
    }
