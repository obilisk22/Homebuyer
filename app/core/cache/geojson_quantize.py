"""Round GeoJSON coordinate precision and drop redundant points."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _round_val(v: float, precision: int) -> float:
    return round(v, precision)


def _quantize_coords(coords: Any, precision: int) -> Any:
    if not coords:
        return coords
    if isinstance(coords[0], (int, float)):
        return [_round_val(float(coords[0]), precision), _round_val(float(coords[1]), precision)]
    return [_quantize_coords(c, precision) for c in coords]


def _dedupe_ring(ring: list, min_ring_points: int) -> list:
    if len(ring) < 2:
        return ring
    out: list = [ring[0]]
    for pt in ring[1:]:
        if pt != out[-1]:
            out.append(pt)
    # close ring if needed
    if len(out) >= 2 and out[0] != out[-1]:
        out.append(out[0])
    elif len(out) >= 2 and out[0] == out[-1] and len(out) > 1:
        pass
    if len(out) < min_ring_points:
        return ring
    return out


def _dedupe_coords(coords: Any, min_ring_points: int) -> Any:
    if not coords:
        return coords
    if isinstance(coords[0], (int, float)):
        return coords
    # polygon: list of rings; linestring: single ring; multipolygon: list of polygons
    if isinstance(coords[0][0], (int, float)):
        return _dedupe_ring(coords, min_ring_points)
    return [_dedupe_coords(c, min_ring_points) for c in coords]


def quantize_geojson(fc: dict, *, precision: int = 5, min_ring_points: int = 4) -> dict:
    out = deepcopy(fc)
    for feature in out.get("features", []):
        geom = feature.get("geometry")
        if not geom or "coordinates" not in geom:
            continue
        coords = _quantize_coords(geom["coordinates"], precision)
        geom["coordinates"] = _dedupe_coords(coords, min_ring_points)
    return out
