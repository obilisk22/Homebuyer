"""Shared geographic helpers."""

from __future__ import annotations

import math


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in miles."""
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def normalize_city(city: str | None) -> str:
    """Lowercase, trim, and collapse internal whitespace."""
    return " ".join((city or "").strip().lower().split())


def point_in_bbox(
    lat: float,
    lng: float,
    bbox: tuple[float, float, float, float],
) -> bool:
    """True when (lat, lng) is inside bbox ``(min_lat, max_lat, min_lng, max_lng)``."""
    min_lat, max_lat, min_lng, max_lng = bbox
    return min_lat <= lat <= max_lat and min_lng <= lng <= max_lng
