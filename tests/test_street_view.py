"""Street View / Earth deep-link helpers (TODO-034 / TODO-035)."""

from app.modules.street_view import (
    earth_open_url,
    maps_search_url,
    street_view_embed_url,
    street_view_open_url,
)
from app.ui import theme as theme_mod


def test_street_view_embed_is_free_svembed():
    url = street_view_embed_url(34.05, -118.25, heading=90)
    assert "output=svembed" in url
    assert "34.05,-118.25" in url
    assert "cbp=11,90,0,0,0" in url


def test_maps_and_pano_open_urls():
    assert "google.com/maps/search" in maps_search_url("1 Main St, LA")
    pano = street_view_open_url(34.05, -118.25)
    assert "map_action=pano" in pano
    assert "viewpoint=34.05,-118.25" in pano


def test_earth_open_url_deep_link():
    url = earth_open_url(34.0522, -118.2437)
    assert url.startswith("https://earth.google.com/web/@")
    assert "34.0522,-118.2437," in url
    assert url.endswith(",100a,1000d,35y,0h,0t,0r")


def test_theme_sv_avoids_min_height_shell():
    css = theme_mod._CSS
    assert ".homebuy-sv" in css
    assert "aspect-ratio: 16 / 9" in css
    assert "max-height: min(42vh, 480px)" in css
    # Forced min-height created empty gutter under the scaled iframe
    sv_block = css.split(".homebuy-sv {", 1)[1].split("}", 1)[0]
    assert "min-height" not in sv_block
