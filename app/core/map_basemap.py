"""Leaflet basemap helpers for the Map tab."""

from __future__ import annotations

from typing import Any

DARK_TILE_URL = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"

DARK_TILE_OPTIONS: dict[str, Any] = {
    "attribution": (
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
        '&copy; <a href="https://carto.com/attributions">CARTO</a>'
    ),
    "subdomains": "abcd",
    "maxZoom": 20,
}

# leaflet.fullscreen — loaded via NiceGUI additional_resources before L.map()
# Icon sprite is also referenced absolutely in theme.py (plugin CSS uses a relative url()).
FULLSCREEN_ICON_URL = (
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet.fullscreen/4.0.0/icon-fullscreen.svg"
)
FULLSCREEN_RESOURCES: list[str] = [
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet.fullscreen/4.0.0/Control.FullScreen.min.css",
    "https://cdnjs.cloudflare.com/ajax/libs/leaflet.fullscreen/4.0.0/Control.FullScreen.min.js",
]

FULLSCREEN_CONTROL_OPTIONS: dict[str, Any] = {
    "position": "topleft",
    "title": "Fullscreen map",
    "titleCancel": "Exit fullscreen",
    "forceSeparateButton": True,
}


def leaflet_map_kwargs() -> dict[str, Any]:
    """Kwargs for ui.leaflet: dark-friendly fullscreen control near zoom."""
    return {
        "options": {
            "fullscreenControl": True,
            "fullscreenControlOptions": dict(FULLSCREEN_CONTROL_OPTIONS),
        },
        "additional_resources": list(FULLSCREEN_RESOURCES),
    }


def apply_dark_basemap(leaflet_map: Any) -> None:
    """Replace NiceGUI's default OSM tiles with CARTO Dark Matter."""
    layers = getattr(leaflet_map, "layers", None)
    if layers:
        # Default OSM tile is added first in nicegui.elements.leaflet.Leaflet.__init__
        leaflet_map.remove_layer(layers[0])
    leaflet_map.tile_layer(url_template=DARK_TILE_URL, options=dict(DARK_TILE_OPTIONS))
