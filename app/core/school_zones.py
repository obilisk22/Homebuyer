"""Assigned school zones via district attendance GIS (LAUSD first)."""

from __future__ import annotations

from typing import Any

import requests

from app.core.overlay_cache import cache_key, read_json, write_json

REQUEST_TIMEOUT_S = 30
CACHE_MAX_AGE_S = 7 * 24 * 3600
CACHE_NS = "school_zones"
CACHE_REV = "v1"

LAUSD_BASE = (
    "https://maps.lacity.org/lahub/rest/services/LAUSD_Schools/MapServer"
)
# level -> (attendance_layer_id, map_type filter for school points)
LAUSD_LEVELS: dict[str, tuple[int, str]] = {
    "elementary": (4, "ES"),
    "middle": (5, "MS"),
    "high": (6, "HS"),
}


def point_in_ring(lng: float, lat: float, ring: list[list[float]]) -> bool:
    """Ray-cast; ring vertices are [lng, lat]."""
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = float(ring[i][0]), float(ring[i][1])
        xj, yj = float(ring[j][0]), float(ring[j][1])
        if ((yi > lat) != (yj > lat)) and (
            lng < (xj - xi) * (lat - yi) / (yj - yi + 0.0) + xi
        ):
            inside = not inside
        j = i
    return inside


def point_in_polygon(
    lng: float, lat: float, rings: list[list[list[float]]]
) -> bool:
    if not rings:
        return False
    if not point_in_ring(lng, lat, rings[0]):
        return False
    for hole in rings[1:]:
        if point_in_ring(lng, lat, hole):
            return False
    return True
