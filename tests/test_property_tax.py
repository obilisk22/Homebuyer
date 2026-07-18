from app.core.property_tax import resolve_annual_property_tax


def test_prefers_explicit_zillow_tax():
    amount, source = resolve_annual_property_tax(
        annual_tax=12_853.69,
        tax_assessed_value=1_214_000,
        property_tax_rate=0.0082,
        list_price=1_200_000,
        lat=34.0,
        lng=-118.5,
    )
    assert amount == 12_853.69
    assert source == "Zillow"


def test_assessed_times_rate_when_no_explicit_tax(monkeypatch):
    # Ensure ACS is not consulted
    monkeypatch.setattr(
        "app.core.property_tax.county_effective_property_tax_rate",
        lambda lat, lng: 0.99,
    )
    amount, source = resolve_annual_property_tax(
        annual_tax=None,
        tax_assessed_value=1_000_000,
        property_tax_rate=0.01,
        list_price=900_000,
        lat=34.0,
        lng=-118.5,
    )
    assert amount == 10_000.0
    assert source == "Zillow assessed × rate"


def test_acs_uses_assessed_when_present(monkeypatch):
    monkeypatch.setattr(
        "app.core.property_tax.county_effective_property_tax_rate",
        lambda lat, lng: 0.01,
    )
    amount, source = resolve_annual_property_tax(
        annual_tax=None,
        tax_assessed_value=800_000,
        property_tax_rate=None,
        list_price=1_000_000,
        lat=34.0,
        lng=-118.5,
    )
    assert amount == 8_000.0
    assert "ACS" in source


def test_acs_falls_back_to_list_price(monkeypatch):
    monkeypatch.setattr(
        "app.core.property_tax.county_effective_property_tax_rate",
        lambda lat, lng: 0.012,
    )
    amount, source = resolve_annual_property_tax(
        annual_tax=None,
        tax_assessed_value=None,
        property_tax_rate=None,
        list_price=500_000,
        lat=47.6,
        lng=-122.3,
    )
    assert amount == 6_000.0
    assert "ACS" in source


def test_unresolved_when_no_data(monkeypatch):
    monkeypatch.setattr(
        "app.core.property_tax.county_effective_property_tax_rate",
        lambda lat, lng: None,
    )
    amount, source = resolve_annual_property_tax(
        annual_tax=None,
        tax_assessed_value=None,
        property_tax_rate=None,
        list_price=500_000,
        lat=None,
        lng=None,
    )
    assert amount is None
    assert source == ""
