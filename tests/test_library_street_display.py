"""TODO-044/045/046 — library Growth caption, street+unit display, appr bands."""

from pathlib import Path

from app.ui import theme

ROOT = Path(__file__).resolve().parents[1]


def test_library_appreciation_caption_uses_growth_label():
    from types import SimpleNamespace

    from app.ui.pages import _library_appreciation_caption

    snap = SimpleNamespace(has_financials=True, appreciation_pct=4.2)
    assert _library_appreciation_caption(snap) == "Growth 4.2%/yr"
    assert "Appr." not in _library_appreciation_caption(snap)


def test_library_appreciation_tone_bands():
    from app.ui.pages import _library_appreciation_tone_class

    assert _library_appreciation_tone_class(2.9) == "hb-appr-low"
    assert _library_appreciation_tone_class(3.0) == ""
    assert _library_appreciation_tone_class(6.0) == ""
    assert _library_appreciation_tone_class(6.1) == "hb-appr-high"


def test_split_street_unit_abbreviates_markers():
    from app.ui.pages import _split_street_unit

    assert _split_street_unit("123 Main St UNIT 2") == ("123 Main St", "#2")
    assert _split_street_unit("123 Main St Apt 4B") == ("123 Main St", "#4B")
    assert _split_street_unit("123 Main St APARTMENT 12") == ("123 Main St", "#12")
    assert _split_street_unit("500 Oak Ave Suite 200") == ("500 Oak Ave", "#200")
    assert _split_street_unit("500 Oak Ave STE 3A") == ("500 Oak Ave", "#3A")
    assert _split_street_unit("123 Main St #4B") == ("123 Main St", "#4B")
    assert _split_street_unit("123 Main St") == ("123 Main St", None)


def test_street_address_line_still_strips_place_then_unit_splits():
    from app.ui.pages import _split_street_unit, _street_address_line

    street = _street_address_line(
        "1234 Neon Ave UNIT 2, Santa Monica, CA 90401",
        city="Santa Monica",
        state="CA",
        zip_code="90401",
    )
    assert street == "1234 Neon Ave UNIT 2"
    assert _split_street_unit(street) == ("1234 Neon Ave", "#2")


def test_theme_has_smaller_address_and_unit_and_high_appr():
    css = theme._CSS
    # ~10% smaller than prior clamp(1.35rem, 4vw, 2.5rem)
    assert "--hb-library-address-size: clamp(1.215rem, 3.6vw, 2.25rem)" in css
    assert ".hb-library-unit" in css
    assert "0.75em" in css
    assert ".hb-appr-high" in css
    assert "hb-neon-3" in css or "#B8FF3C" in css or "var(--hb-neon-3)" in css


def test_pages_render_unit_span_and_growth_bands():
    src = (ROOT / "app" / "ui" / "pages.py").read_text(encoding="utf-8")
    assert 'f"Growth ' in src
    assert 'f"Appr.' not in src
    assert "_split_street_unit" in src
    assert "_render_street_address" in src
    assert "hb-library-unit" in src
    assert "hb-appr-high" in src
    assert "_library_appreciation_tone_class" in src
