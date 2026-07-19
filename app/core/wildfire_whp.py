"""USFS Wildfire Hazard Potential (WHP) 2023 — free WMS overlay (no API key).

Uses the Rocky Mountain Research Station classified WHP MapServer WMS, same
pattern as FEMA NFHL flood tiles. Classes: very low → very high (plus
non-burnable / water in the source raster).

WMS::

    https://apps.fs.usda.gov/arcx/services/RDW_Wildfire/
    RMRS_WildfireHazardPotential_2023/MapServer/WMSServer

If the Forest Service endpoint is down, the Map tab should clear the toggle
and show a status error (no local raster fallback in v1).
"""

from __future__ import annotations

# CONUS classified WHP — layer 0 is the standard-color CONUS classes layer.
USFS_WHP_WMS_URL = (
    "https://apps.fs.usda.gov/arcx/services/RDW_Wildfire/"
    "RMRS_WildfireHazardPotential_2023/MapServer/WMSServer"
)

USFS_WHP_WMS_OPTIONS: dict = {
    "layers": "0",
    "format": "image/png",
    "transparent": True,
    "opacity": 0.55,
    "attribution": "USFS RMRS Wildfire Hazard Potential 2023",
    "maxZoom": 18,
}

WHP_LEGEND: list[tuple[str, str]] = [
    ("Very low", "#2E7D32"),
    ("Low", "#9CCC65"),
    ("Moderate", "#FFC107"),
    ("High", "#FF7043"),
    ("Very high", "#FF2BD6"),
]


def wildfire_wms_layer_args() -> tuple[str, dict]:
    """Return (url, options) for NiceGUI ``ui.leaflet(...).wms_layer``."""
    return USFS_WHP_WMS_URL, dict(USFS_WHP_WMS_OPTIONS)
