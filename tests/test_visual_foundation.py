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
    src = (ROOT / "app" / "ui" / "pages.py").read_text(encoding="utf-8")
    assert "hb-library-address" in src
    assert "hb-library-price" in src
    assert "_street_address_line" in src
    assert "hb-page-title" in src
    assert "hb-empty-state" in src
    assert "hb-library-shell" in src


def test_library_nav_and_filter_ux():
    src = (ROOT / "app" / "ui" / "pages.py").read_text(encoding="utf-8")
    assert 'classes("hb-brand")' in src
    assert 'brand.on("click"' in src
    assert 'ui.button("Apply"' in src
    assert "0 homes" in src
    assert "Filter · {active} active" in src
    assert 'ui.button("Back",' not in src
    assert "text-subtitle1" not in src
    assert "hb-page-meta" in src


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
