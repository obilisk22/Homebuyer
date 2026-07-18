"""Resolve annual property tax from listing facts + Census ACS county rates."""

from __future__ import annotations

from app.core.census_acs import county_effective_property_tax_rate


def resolve_annual_property_tax(
    *,
    annual_tax: float | None,
    tax_assessed_value: float | None,
    property_tax_rate: float | None,
    list_price: float | None,
    lat: float | None,
    lng: float | None,
) -> tuple[float | None, str]:
    if annual_tax is not None and annual_tax > 0:
        return float(annual_tax), "Zillow"

    if (
        tax_assessed_value is not None
        and tax_assessed_value > 0
        and property_tax_rate is not None
        and property_tax_rate > 0
    ):
        return float(tax_assessed_value) * float(property_tax_rate), "Zillow assessed × rate"

    basis: float | None = None
    if tax_assessed_value is not None and tax_assessed_value > 0:
        basis = float(tax_assessed_value)
    elif list_price is not None and list_price > 0:
        basis = float(list_price)

    if basis is not None and lat is not None and lng is not None:
        rate = county_effective_property_tax_rate(float(lat), float(lng))
        if rate is not None and rate > 0:
            return basis * rate, "Estimated: ACS county"

    return None, ""
