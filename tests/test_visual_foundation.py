from pathlib import Path

from app.ui import theme

ROOT = Path(__file__).resolve().parents[1]


def test_fonts_readme_documents_akira_and_creato():
    readme = ROOT / "app" / "static" / "fonts" / "README.md"
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    assert "Akira Expanded" in text
    assert "Creato Display" in text
    assert "personal" in text.lower()
    assert "OFL" in text or "Open Font License" in text


def test_main_registers_static_files():
    src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert 'add_static_files("/static"' in src


def test_theme_css_has_visual_foundation_tokens():
    css = theme._CSS
    assert "--hb-font-display" in css
    assert "--hb-font-body" in css
    assert ".hb-library-address" in css
    assert "Akira" in css or "hb-font-display" in css
    assert "Creato" in css or "hb-font-body" in css
    assert "--hb-library-price-size" in css
    assert "--hb-library-address-size" in css
    assert ".hb-page-title" in css
    assert ".hb-empty-state" in css
    assert "clamp(" in css


def test_akira_font_face_registered_when_file_present():
    akira = (
        ROOT
        / "app"
        / "static"
        / "fonts"
        / "akira_expanded"
        / "Akira Expanded Demo.otf"
    )
    if not akira.is_file():
        return
    assert "Akira Expanded" in theme._FONT_FACES
    assert "akira_expanded" in theme._FONT_FACES
    # Super Bold cut mapped across weights so browser matching succeeds
    assert theme._FONT_FACES.count("Akira Expanded") >= 2


def test_library_page_uses_address_and_price_classes():
    src = (
        (ROOT / "app" / "ui" / "library_page.py").read_text(encoding="utf-8")
        + (ROOT / "app" / "ui" / "chip_helpers.py").read_text(encoding="utf-8")
    )
    assert "hb-library-address" in src
    assert "hb-library-price" in src
    assert "_street_address_line" in src
    assert "hb-page-title" in src
    assert "hb-empty-state" in src
    assert "hb-library-shell" in src


def test_property_header_photo_modes():
    src = (ROOT / "app" / "ui" / "property_page.py").read_text(encoding="utf-8")
    assert 'PROPERTY_HEADER_PHOTO_MODE = "bleed"' in src
    assert "hb-property-hero" in src
    assert "hb-property-hero__scrim" in src
    assert 'mode == "beside"' in src
    css = theme._CSS
    assert ".hb-property-hero--bleed" in css
    assert ".hb-property-hero--beside" in css
    assert ".hb-property-hero__bg" in css


def test_library_nav_and_filter_ux():
    src = (
        (ROOT / "app" / "ui" / "pages.py").read_text(encoding="utf-8")
        + (ROOT / "app" / "ui" / "library_page.py").read_text(encoding="utf-8")
    )
    assert 'classes("hb-brand")' in src
    assert 'brand.on("click"' in src
    assert 'ui.button("Apply"' in src
    assert "0 homes" in src
    assert "Filter · {active} active" in src
    assert 'ui.button("Back",' not in src
    assert "text-subtitle1" not in src
    assert "hb-page-meta" in src


def test_library_cards_render_nearby_signal_chips():
    src = (
        (ROOT / "app" / "ui" / "library_page.py").read_text(encoding="utf-8")
        + (ROOT / "app" / "ui" / "chip_helpers.py").read_text(encoding="utf-8")
    )
    assert "parse_signals_json" in src
    assert "hits_in_order" in src
    assert "tooltip_for" in src
    assert "source_url_for" in src
    assert "home_lat=" in src
    assert "home_lng=" in src
    assert "ICON_BY_KEY" in src
    assert "RISK_KEYS" in src
    assert "hb-nearby-icons" in src
    assert "hb-nearby-chip--{kind}" in src
    assert "_render_nearby_signal_chips" in src
    assert "listing_risk_chips" in src
    assert "ui.navigate.to" in src
    assert "new_tab=True" in src
    assert "refresh_stale_nearby_signals_job, limit=3" in src
    assert "ui.timer(0.1, _refresh_stale_nearby_after_paint, once=True)" in src
    refresh_body = src.split("        def refresh() -> None:", 1)[1].split(
        "        async def _refresh_stale_nearby_after_paint() -> None:", 1
    )[0]
    assert "refresh_stale_nearby_signals" not in refresh_body


def test_property_header_nearby_and_edit_listing():
    src = (
        (ROOT / "app" / "ui" / "property_page.py").read_text(encoding="utf-8")
        + (ROOT / "app" / "ui" / "chip_helpers.py").read_text(encoding="utf-8")
    )
    assert "hb-edit-listing-expansion" in src
    assert "_render_nearby_signal_chips(" in src
    assert "listing_risk_chips" in src
    assert "nearby_signals = prop.nearby_signals or \"\"" in src
    assert "_library_appreciation_caption" in src
    assert "hb-appr-low" in src
    css = theme._CSS
    assert ".hb-edit-listing-expansion" in css
    assert ".hb-appr-low" in css
    assert ".hb-property-hero:has(.hb-nearby-icons)" in css


def test_theme_styles_nearby_signal_chips():
    css = theme._CSS
    assert ".hb-nearby-icons" in css
    assert ".hb-nearby-chip" in css
    assert ".hb-nearby-chip--risk" in css
    assert ".hb-nearby-chip--amenity" in css
    assert "pointer-events: none" in css
    assert "right: 0.85rem" in css
    assert ".hb-library-card:has(.hb-nearby-icons)" in css


def test_financial_rent_control_wires_growth_into_projection():
    src = (ROOT / "app" / "modules" / "financial.py").read_text(encoding="utf-8")

    assert "ui.checkbox(" in src
    assert '"Rent control"' in src
    assert "growth_state" in src
    assert "ensure_rent_growth(" in src
    assert "rent_control=checked" in src
    assert 'rent_growth_pct=float(growth_state["pct"] or 0)' in src
    assert '"rent_control": bool(growth_state["control"])' in src
    assert '"rent_growth_pct": float(growth_state["pct"] or 0)' in src


def test_financial_inputs_defer_dom_updates_while_typing():
    """Avoid NiceGUI controlled-input rebind (backwards typing / cursor jump)."""
    src = (ROOT / "app" / "modules" / "financial.py").read_text(encoding="utf-8")

    assert "offer_in.on_value_change" not in src
    assert "list_in.on_value_change" not in src
    assert "down.on_value_change" not in src
    assert "term.on_value_change" not in src
    assert 'term.on("blur"' in src
    assert "_sync_rate_source_caption()" in src
    assert "refresh_down_meta()" in src
    assert '_mark_rate_manual(_: object = None) -> None:\n                if suppress_rate_manual["on"]:\n                    return\n                # State only' in src


def test_street_address_line_strips_city_state_zip():
    from app.ui.pages import _street_address_line

    assert (
        _street_address_line(
            "1234 Neon Ave UNIT 2, Santa Monica, CA 90401",
            city="Santa Monica",
            state="CA",
            zip_code="90401",
        )
        == "1234 Neon Ave UNIT 2"
    )
    assert _street_address_line("123 Main St") == "123 Main St"
