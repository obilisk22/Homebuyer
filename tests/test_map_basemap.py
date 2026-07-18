from app.core.map_basemap import (
    DARK_TILE_OPTIONS,
    DARK_TILE_URL,
    FULLSCREEN_ICON_URL,
    FULLSCREEN_RESOURCES,
    leaflet_map_kwargs,
)
from app.ui import theme as theme_mod


def test_dark_tile_url_is_carto_dark_all():
    assert "basemaps.cartocdn.com" in DARK_TILE_URL
    assert "dark_all" in DARK_TILE_URL


def test_dark_tile_options_have_attribution_and_subdomains():
    assert "CARTO" in DARK_TILE_OPTIONS["attribution"] or "carto" in DARK_TILE_OPTIONS["attribution"].lower()
    assert "OpenStreetMap" in DARK_TILE_OPTIONS["attribution"] or "openstreetmap" in DARK_TILE_OPTIONS["attribution"].lower()
    assert DARK_TILE_OPTIONS.get("subdomains") == "abcd"
    assert int(DARK_TILE_OPTIONS.get("maxZoom", 0)) >= 18


def test_leaflet_map_kwargs_enable_fullscreen_plugin():
    kwargs = leaflet_map_kwargs()
    assert kwargs["options"]["fullscreenControl"] is True
    assert kwargs["options"]["fullscreenControlOptions"]["position"] == "topleft"
    assert kwargs["options"]["fullscreenControlOptions"]["forceSeparateButton"] is True
    assert kwargs["additional_resources"] == FULLSCREEN_RESOURCES
    assert any(url.endswith("Control.FullScreen.min.js") for url in kwargs["additional_resources"])
    assert any(url.endswith("Control.FullScreen.min.css") for url in kwargs["additional_resources"])


def test_theme_preserves_fullscreen_icon_background_image():
    """Regression: background shorthand on .leaflet-bar a must not wipe the icon."""
    css = theme_mod._CSS
    assert FULLSCREEN_ICON_URL in css
    assert f'background-image: url("{FULLSCREEN_ICON_URL}")' in css
    zoom_block = css.split(".leaflet-bar a {", 1)[1].split("}", 1)[0]
    assert "background-color:" in zoom_block
    assert "background:" not in zoom_block
    # Black SVG sprite → white via invert (no cyan hue-rotate)
    assert "filter: invert(1);" in css
    assert "hue-rotate" not in css.split(".leaflet-control-fullscreen", 1)[1]
