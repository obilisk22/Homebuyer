"""TODO-039: cooling scrape, central-AC classification, library risk chips."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.listing_signals import (
    central_ac_risk_entry,
    classify_has_central_ac,
    format_cooling_label,
    listing_risk_chips,
)
from app.core.zillow_listing import (
    extract_listing_details,
    normalize_cooling,
)


def test_normalize_cooling_joins_list():
    assert normalize_cooling(["Central Air", "Ceiling Fan"]) == "Central Air, Ceiling Fan"
    assert normalize_cooling("Window Unit") == "Window Unit"
    assert normalize_cooling(None) == ""
    assert normalize_cooling([]) == ""


@pytest.mark.parametrize(
    ("cooling", "expected"),
    [
        ("", None),
        ("Central Air", True),
        ("Central A/C", True),
        ("CENTRAL AIR CONDITIONING", True),
        ("Central, Ceiling Fan", True),
        ("Window Unit", False),
        ("Window units", False),
        ("Wall", False),
        ("Wall Unit", False),
        ("Evaporative Cooler", False),
        ("Swamp Cooler", False),
        ("None", False),
        ("No A/C", False),
        ("No AC", False),
        ("Ductless / Mini-Split", False),
        ("Mini Split", False),
        # Central wins when both present
        ("Central Air, Window Unit", True),
        # Ambiguous — do not false-alarm
        ("Other", None),
        ("Yes", None),
        ("Refrigeration", None),
        ("Ceiling Fan", None),
    ],
)
def test_classify_has_central_ac(cooling: str, expected: bool | None):
    assert classify_has_central_ac(cooling) is expected


def test_extract_cooling_from_reso_facts_list():
    html = (
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"componentProps":{"gdpClientCache":"'
        '{\\"zpid\\":1,\\"price\\":800000,\\"bedrooms\\":3,'
        '\\"resoFacts\\":{\\"cooling\\":[\\"Central Air\\"]}}"'
        '}}}}'
        "</script>"
    )
    details = extract_listing_details(html)
    assert details.cooling == "Central Air"
    assert details.has_central_ac is True


def test_extract_cooling_window_units():
    html = (
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"componentProps":{"gdpClientCache":"'
        '{\\"zpid\\":2,\\"price\\":700000,\\"livingArea\\":1100,'
        '\\"resoFacts\\":{\\"cooling\\":[\\"Window Unit\\"]}}"'
        '}}}}'
        "</script>"
    )
    details = extract_listing_details(html)
    assert details.cooling == "Window Unit"
    assert details.has_central_ac is False


def test_extract_cooling_none():
    html = (
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"componentProps":{"gdpClientCache":"'
        '{\\"zpid\\":3,\\"price\\":500000,'
        '\\"resoFacts\\":{\\"cooling\\":[\\"None\\"]}}"'
        '}}}}'
        "</script>"
    )
    details = extract_listing_details(html)
    assert details.cooling == "None"
    assert details.has_central_ac is False


def test_extract_cooling_string_field():
    html = (
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"componentProps":{"gdpClientCache":"'
        '{\\"zpid\\":4,\\"price\\":600000,\\"cooling\\":\\"Evaporative\\"}"'
        '}}}}'
        "</script>"
    )
    details = extract_listing_details(html)
    assert details.cooling == "Evaporative"
    assert details.has_central_ac is False


def test_extract_cooling_from_escaped_regex():
    html = (
        "<html><body>"
        r'\"cooling\":[\"Wall Unit\"],'
        r'\"price\":650000'
        "</body></html>"
    )
    details = extract_listing_details(html)
    assert "Wall" in details.cooling
    assert details.has_central_ac is False


def test_extract_cooling_missing_is_unknown():
    html = (
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"componentProps":{"gdpClientCache":"'
        '{\\"zpid\\":5,\\"price\\":900000,\\"bedrooms\\":4}"'
        '}}}}'
        "</script>"
    )
    details = extract_listing_details(html)
    assert details.cooling == ""
    assert details.has_central_ac is None


def test_central_ac_risk_entry_only_when_clearly_absent():
    assert central_ac_risk_entry(SimpleNamespace(has_central_ac=True, cooling="Central Air")) is None
    assert central_ac_risk_entry(SimpleNamespace(has_central_ac=None, cooling="")) is None
    assert central_ac_risk_entry(SimpleNamespace(has_central_ac=None, cooling="Other")) is None

    entry = central_ac_risk_entry(
        SimpleNamespace(has_central_ac=False, cooling="Window Unit")
    )
    assert entry is not None
    assert entry["key"] == "no_central_ac"
    assert entry["kind"] == "risk"
    assert entry["icon"] == "ac_unit"
    assert "No central AC" in entry["tooltip"]
    assert "Window Unit" in entry["tooltip"]


def test_format_cooling_label_and_listing_risk_chips():
    assert format_cooling_label("Window Unit") == "Window Unit"
    assert format_cooling_label("") == ""

    chips = listing_risk_chips(
        SimpleNamespace(has_central_ac=False, cooling="None")
    )
    assert len(chips) == 1
    assert chips[0]["key"] == "no_central_ac"

    assert listing_risk_chips(SimpleNamespace(has_central_ac=True, cooling="Central Air")) == []
    assert listing_risk_chips(SimpleNamespace(has_central_ac=None, cooling="")) == []


def test_property_model_has_cooling_columns():
    from app.core.models import Property

    assert Property.__table__.c.cooling.type.length == 256
    assert Property.__table__.c.has_central_ac.nullable is True
