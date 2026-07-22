"""USDOT BTS National Transportation Noise Map — free ArcGIS tile overlay.

CONUS multimodal (aviation + road + rail) 2020 LAeq screening layer.
TilesOnly MapServer — use XYZ tiles, not WMS/export.

Disclaimer: BTS intends this for national trend / screening analysis, not
parcel-precise or regulatory noise assessment.
"""

from __future__ import annotations

BTS_NOISE_MAPSERVER = (
    "https://geo.dot.gov/server/rest/services/Hosted/"
    "NTAD_Noise_2020_CONUS_Aviation_Road_Rail/MapServer"
)

# ArcGIS REST XYZ: {z}/{y}/{x} (not OSM {z}/{x}/{y}).
BTS_NOISE_TILE_URL = f"{BTS_NOISE_MAPSERVER}/tile/{{z}}/{{y}}/{{x}}"

BTS_NOISE_TILE_OPTIONS: dict = {
    "opacity": 0.55,
    "maxZoom": 18,
    "attribution": (
        "USDOT BTS — National Transportation Noise Map (2020)"
    ),
}

NOISE_LEGEND: list[tuple[str, str]] = [
    ("Lower", "#2E7D32"),
    ("Moderate", "#FFC107"),
    ("Higher", "#FF2BD6"),
]

NOISE_STATUS_DISCLAIMER = (
    "Noise: BTS 2020 aviation+road+rail screening (trend context, not parcel-precise)"
)


def noise_tile_layer_args() -> tuple[str, dict]:
    """Return (url_template, options) for Leaflet ``tileLayer``."""
    return BTS_NOISE_TILE_URL, dict(BTS_NOISE_TILE_OPTIONS)
