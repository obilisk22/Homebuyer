"""Air quality near pin — Open-Meteo US AQI grid (free, no API key).

Samples a small lat/lng grid around the pin via the Open-Meteo Air Quality
API (batched multi-location request) and paints hex cells in the same visual
language as the crime density layer.

Open-Meteo is preferred over AirNow / OpenAQ because those require developer
keys; if the API is flaky we degrade with a clear status message and keep any
warm cache.
"""

from __future__ import annotations

import math
from typing import Any

import requests

from app.core.crime_density import HEX_SIZE_DEG, axial_from_lng_lat, hex_cell_polygon
from app.core.overlay_cache import cache_key, read_json, write_json

REQUEST_TIMEOUT_S = 30
CACHE_MAX_AGE_S = 2 * 3600  # AQI changes; short TTL
DEFAULT_HALF_SPAN_DEG = 0.04
GRID_STEP_DEG = 0.02
OPEN_METEO_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# US AQI category breaks → cyberpunk fills.
AQI_BREAKS: list[tuple[float, str]] = [
    (50, "#00E5FF"),  # Good
    (100, "#B8FF3C"),  # Moderate
    (150, "#FFC107"),  # Unhealthy for sensitive
    (200, "#FF7043"),  # Unhealthy
    (300, "#FF2BD6"),  # Very unhealthy
    (10**9, "#9C27B0"),  # Hazardous
]

AQI_LEGEND: list[tuple[str, str]] = [
    ("0–50 Good", "#00E5FF"),
    ("51–100 Moderate", "#B8FF3C"),
    ("101–150 Sensitive", "#FFC107"),
    ("151–200 Unhealthy", "#FF7043"),
    ("201–300 Very unhealthy", "#FF2BD6"),
    ("301+ Hazardous", "#9C27B0"),
]


def aqi_fill_color(aqi: float | None) -> str:
    if aqi is None or not math.isfinite(aqi):
        return "#2A3340"
    for threshold, color in AQI_BREAKS:
        if aqi <= threshold:
            return color
    return AQI_BREAKS[-1][1]


def aqi_category(aqi: float | None) -> str:
    if aqi is None or not math.isfinite(aqi):
        return "Unknown"
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Moderate"
    if aqi <= 150:
        return "Unhealthy for sensitive groups"
    if aqi <= 200:
        return "Unhealthy"
    if aqi <= 300:
        return "Very unhealthy"
    return "Hazardous"


def _as_float(raw: object) -> float | None:
    if raw is None:
        return None
    try:
        val = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(val) or val < 0:
        return None
    return val


def parse_open_meteo_current(payload: dict[str, Any]) -> float | None:
    """Extract US AQI from a single-location Open-Meteo air-quality body."""
    current = payload.get("current") or {}
    val = _as_float(current.get("us_aqi"))
    if val is not None:
        return val
    hourly = payload.get("hourly") or {}
    series = hourly.get("us_aqi") or []
    if series:
        return _as_float(series[0])
    return None


def parse_open_meteo_batch(
    payload: dict[str, Any] | list[Any],
    coords: list[tuple[float, float]],
) -> list[dict[str, Any]]:
    """Parse multi-location Open-Meteo response → ``[{lat,lng,aqi}, ...]``."""
    samples: list[dict[str, Any]] = []
    if isinstance(payload, list):
        bodies = [b for b in payload if isinstance(b, dict)]
    elif isinstance(payload, dict) and isinstance(payload.get("current"), list):
        # Multi-location: parallel arrays under current.us_aqi
        current = payload["current"]
        # Unusual shape — fall through to single
        bodies = [payload]
    else:
        bodies = [payload] if isinstance(payload, dict) else []

    # Open-Meteo multi-location returns a JSON **array** of location objects.
    if len(bodies) == 1 and len(coords) > 1 and parse_open_meteo_current(bodies[0]) is not None:
        # Single body for multi coords: replicate (API fell back) — rare.
        aqi = parse_open_meteo_current(bodies[0])
        if aqi is not None:
            for lat, lng in coords:
                samples.append({"lat": lat, "lng": lng, "aqi": aqi})
        return samples

    for i, body in enumerate(bodies):
        aqi = parse_open_meteo_current(body)
        if aqi is None:
            continue
        if i < len(coords):
            lat, lng = coords[i]
        else:
            try:
                lat = float(body.get("latitude"))
                lng = float(body.get("longitude"))
            except (TypeError, ValueError):
                continue
        samples.append({"lat": lat, "lng": lng, "aqi": aqi})
    return samples


def _grid_points(
    lat: float, lng: float, half_span_deg: float, step: float
) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    n = max(1, int(round(half_span_deg / step)))
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            pts.append((lat + i * step, lng + j * step))
    return pts


def _fetch_aqi_batch(coords: list[tuple[float, float]]) -> list[dict[str, Any]]:
    if not coords:
        return []
    lats = ",".join(f"{lat:.5f}" for lat, _ in coords)
    lngs = ",".join(f"{lng:.5f}" for _, lng in coords)
    resp = requests.get(
        OPEN_METEO_URL,
        params={
            "latitude": lats,
            "longitude": lngs,
            "current": "us_aqi",
            "timezone": "auto",
        },
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    payload = resp.json()
    return parse_open_meteo_batch(payload, coords)


def fetch_aqi_samples(
    lat: float,
    lng: float,
    *,
    half_span_deg: float = DEFAULT_HALF_SPAN_DEG,
    step: float = GRID_STEP_DEG,
) -> list[dict[str, Any]]:
    """Sample US AQI on a coarse grid (one batched request, cached)."""
    key = cache_key(
        "aqi",
        f"{lat:.3f}",
        f"{lng:.3f}",
        f"{half_span_deg:.3f}",
        f"{step:.3f}",
    )
    cached = read_json("air_quality", key, max_age_s=CACHE_MAX_AGE_S)
    if isinstance(cached, dict) and isinstance(cached.get("samples"), list):
        return list(cached["samples"])

    coords = _grid_points(lat, lng, half_span_deg, step)
    try:
        samples = _fetch_aqi_batch(coords)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Air quality service unavailable (Open-Meteo): {exc}"
        ) from exc

    if not samples:
        raise RuntimeError(
            "Air quality service returned no US AQI samples near this pin."
        )

    write_json("air_quality", key, {"samples": samples})
    return samples


def build_aqi_geojson(
    lat: float,
    lng: float,
    *,
    half_span_deg: float = DEFAULT_HALF_SPAN_DEG,
) -> dict[str, Any]:
    """Hex choropleth of mean US AQI near the pin."""
    samples = fetch_aqi_samples(lat, lng, half_span_deg=half_span_deg)
    bins: dict[tuple[int, int], list[float]] = {}
    for s in samples:
        try:
            slat = float(s["lat"])
            slng = float(s["lng"])
            aqi = float(s["aqi"])
        except (KeyError, TypeError, ValueError):
            continue
        cell = axial_from_lng_lat(slng, slat, HEX_SIZE_DEG)
        bins.setdefault(cell, []).append(aqi)

    features: list[dict[str, Any]] = []
    for (q, r), vals in bins.items():
        mean = sum(vals) / len(vals)
        color = aqi_fill_color(mean)
        ring = hex_cell_polygon(q, r, HEX_SIZE_DEG)
        cat = aqi_category(mean)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {
                    "aqi": round(mean, 1),
                    "fillColor": color,
                    "popup": f"US AQI: {mean:.0f}<br>{cat}<br>(Open-Meteo)",
                },
            }
        )

    pin_aqi = None
    if samples:
        best = min(
            samples,
            key=lambda s: (float(s["lat"]) - lat) ** 2 + (float(s["lng"]) - lng) ** 2,
        )
        pin_aqi = float(best["aqi"])

    msg = "No AQI samples near pin"
    if pin_aqi is not None:
        msg = f"AQI near pin ≈ {pin_aqi:.0f} ({aqi_category(pin_aqi)}) · Open-Meteo"

    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "samples": len(samples),
            "cells": len(features),
            "pin_aqi": pin_aqi,
            "message": msg,
            "source": "Open-Meteo Air Quality (US AQI)",
        },
    }
