"""FEMA National Flood Hazard Layer (NFHL) WMS helpers for Leaflet."""

from __future__ import annotations

# Public NFHL WMS — no API key. Layer 28 = Flood Hazard Zones (NFHLWMS).
FEMA_NFHL_WMS_URL = (
    "https://hazards.fema.gov/arcgis/services/public/NFHLWMS/MapServer/WMSServer"
)

FEMA_FLOOD_WMS_OPTIONS: dict = {
    "layers": "28",
    "format": "image/png",
    "transparent": True,
    "opacity": 0.55,
    "attribution": "FEMA NFHL",
    "maxZoom": 19,
}


def flood_wms_layer_args() -> tuple[str, dict]:
    """Return (url, options) for NiceGUI ``ui.leaflet(...).wms_layer``."""
    return FEMA_NFHL_WMS_URL, dict(FEMA_FLOOD_WMS_OPTIONS)
