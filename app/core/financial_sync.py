from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.finance import blend_appreciation_rates
from app.core.fhfa_hpi import zip5_cagr
from app.core.home_insurance import resolve_annual_insurance
from app.core.home_maintenance import resolve_monthly_maintenance
from app.core.models import DEFAULT_MONTHLY_RENT, FinancialAssumptions, Property
from app.core.mortgage_rates import resolve_interest_rate, should_autofill_interest_rate
from app.core.property_tax import resolve_annual_property_tax
from app.core.utilities import resolve_monthly_utilities
from app.core.zillow_listing import ListingDetails


def resolve_rent_growth(fin: FinancialAssumptions, prop: Property) -> None:
    """Resolve rent growth from control status, ACS county data, or a default."""
    if fin.rent_control:
        fin.rent_growth_pct = 2.0
        fin.rent_growth_source = "Rent control 2%"
        return
    if (fin.rent_growth_source or "").strip() == "Manual":
        return

    cagr = None
    try:
        if prop.latitude is not None and prop.longitude is not None:
            from app.core.census_acs import county_median_rent_cagr

            cagr = county_median_rent_cagr(float(prop.latitude), float(prop.longitude))
    except Exception:  # noqa: BLE001 - data resolution must not block listing sync
        cagr = None

    if cagr is not None:
        fin.rent_growth_pct = float(cagr)
        fin.rent_growth_source = "ACS county ~5y CAGR"
    else:
        fin.rent_growth_pct = 3.0
        fin.rent_growth_source = "Default"


def apply_mortgage_rate_autofill(
    fin: FinancialAssumptions,
    *,
    rate_resolver: Callable[..., tuple[float | None, str]] = resolve_interest_rate,
) -> None:
    """Fill interest rate from Freddie Mac PMMS for the current loan term."""
    if not should_autofill_interest_rate(fin.interest_rate_source):
        return
    term = int(fin.loan_term_years or 30)
    rate, src = rate_resolver(term)
    if rate is None or rate <= 0:
        return
    fin.interest_rate_pct = float(rate)
    fin.interest_rate_source = src


def apply_maintenance_autofill(
    fin: FinancialAssumptions,
    prop: Property,
    details: ListingDetails,
    *,
    maintenance_resolver: Callable[..., tuple[float | None, str]] = resolve_monthly_maintenance,
) -> None:
    """Fill monthly maintenance unless the buyer set Manual."""
    if (fin.maintenance_source or "").strip() == "Manual":
        return

    price = None
    if fin.list_price and fin.list_price > 0:
        price = float(fin.list_price)
    elif details.list_price and details.list_price > 0:
        price = float(details.list_price)
    elif prop.list_price and prop.list_price > 0:
        price = float(prop.list_price)

    offer = float(fin.offer_price or 0) or None
    sqft = None
    if prop.sqft and prop.sqft > 0:
        sqft = float(prop.sqft)
    elif details.sqft and details.sqft > 0:
        sqft = float(details.sqft)

    year_built = None
    if prop.year_built:
        try:
            year_built = int(prop.year_built)
        except (TypeError, ValueError):
            year_built = None
    if year_built is None and details.year_built:
        try:
            year_built = int(details.year_built)
        except (TypeError, ValueError):
            year_built = None

    state = (details.state or prop.state or "").strip()
    amt, src = maintenance_resolver(
        list_price=price,
        offer_price=offer,
        sqft=sqft,
        year_built=year_built,
        state=state,
    )
    if amt is not None and amt > 0:
        fin.monthly_maintenance = float(amt)
        fin.maintenance_source = src
    else:
        fin.monthly_maintenance = 0.0
        fin.maintenance_source = ""


def apply_utilities_autofill(
    fin: FinancialAssumptions,
    prop: Property,
    details: ListingDetails,
    *,
    utilities_resolver: Callable[..., tuple[float | None, str]] = resolve_monthly_utilities,
) -> None:
    """Fill monthly utilities unless the buyer set Manual. Never raises."""
    if (fin.utilities_source or "").strip() == "Manual":
        return
    try:
        sqft = None
        if prop.sqft and prop.sqft > 0:
            sqft = float(prop.sqft)
        elif details.sqft and details.sqft > 0:
            sqft = float(details.sqft)

        year_built = None
        if prop.year_built:
            try:
                year_built = int(prop.year_built)
            except (TypeError, ValueError):
                year_built = None
        if year_built is None and details.year_built:
            try:
                year_built = int(details.year_built)
            except (TypeError, ValueError):
                year_built = None

        city = (details.city or prop.city or "").strip()
        state = (details.state or prop.state or "").strip()
        zip_code = (details.zip_code or prop.zip_code or "").strip()
        amt, src = utilities_resolver(
            sqft=sqft,
            year_built=year_built,
            city=city or None,
            state=state or None,
            zip_code=zip_code or None,
        )
        if amt is not None and amt > 0:
            fin.monthly_utilities = float(amt)
            fin.utilities_source = src
        else:
            fin.monthly_utilities = 0.0
            fin.utilities_source = ""
    except Exception:  # noqa: BLE001 - never break add/sync on utilities
        return


def sync_financial_from_listing(
    session: Session,
    prop: Property,
    details: ListingDetails,
    *,
    rent_growth_resolver: Callable[[FinancialAssumptions, Property], None] | None = None,
    tax_resolver: Callable[..., tuple[float | None, str]] = resolve_annual_property_tax,
    insurance_resolver: Callable[..., tuple[float | None, str]] = resolve_annual_insurance,
    fhfa_resolver: Callable[[str], float | None] = zip5_cagr,
    appreciation_blender: Callable[..., tuple[float, str]] = blend_appreciation_rates,
    rate_resolver: Callable[..., tuple[float | None, str]] = resolve_interest_rate,
    maintenance_resolver: Callable[..., tuple[float | None, str]] = resolve_monthly_maintenance,
    utilities_resolver: Callable[..., tuple[float | None, str]] = resolve_monthly_utilities,
) -> None:
    """Overwrite listing-derived Financials fields; preserve Manual loan inputs."""
    del session  # The attached ORM graph is updated in place; caller owns the transaction.
    if prop.financial is None:
        prop.financial = FinancialAssumptions()
    fin = prop.financial

    if details.list_price is not None and details.list_price > 0:
        fin.list_price = float(details.list_price)
        fin.purchase_price = float(details.list_price)
    elif details.list_price is not None:
        fin.list_price = 0.0
        fin.purchase_price = 0.0

    if details.hoa_fee is not None:
        fin.monthly_hoa = float(details.hoa_fee)

    price_for_tax = None
    if fin.list_price and fin.list_price > 0:
        price_for_tax = float(fin.list_price)
    elif details.list_price and details.list_price > 0:
        price_for_tax = float(details.list_price)
    elif prop.list_price and prop.list_price > 0:
        price_for_tax = float(prop.list_price)

    tax_amt, tax_src = tax_resolver(
        annual_tax=details.annual_tax,
        tax_assessed_value=details.tax_assessed_value,
        property_tax_rate=details.property_tax_rate,
        list_price=price_for_tax,
        lat=prop.latitude,
        lng=prop.longitude,
    )
    if tax_amt is not None and tax_amt > 0:
        fin.annual_property_tax = float(tax_amt)
        fin.property_tax_source = tax_src
    else:
        fin.annual_property_tax = 0.0
        fin.property_tax_source = ""

    state = (details.state or prop.state or "").strip()
    ins_amt, ins_src = insurance_resolver(
        annual_insurance=details.annual_insurance,
        list_price=price_for_tax,
        state=state,
    )
    if ins_amt is not None and ins_amt > 0:
        fin.annual_insurance = float(ins_amt)
        fin.insurance_source = ins_src
    else:
        fin.annual_insurance = 0.0
        fin.insurance_source = ""

    rent_src = (fin.rent_source or "").strip()
    if rent_src in ("", "Zillow", "Default"):
        if details.rent_zestimate is not None and details.rent_zestimate > 0:
            fin.monthly_rent = float(details.rent_zestimate)
            fin.rent_source = "Zillow"
        else:
            fin.monthly_rent = float(DEFAULT_MONTHLY_RENT)
            fin.rent_source = "Default"
    (rent_growth_resolver or resolve_rent_growth)(fin, prop)

    fhfa = None
    try:
        zip_code = (prop.zip_code or details.zip_code or "").strip()
        if zip_code:
            fhfa = fhfa_resolver(zip_code)
    except Exception:
        fhfa = None
    if fhfa is not None:
        fin.appreciation_fhfa_pct = float(fhfa)

    if details.appreciation_decade_pct is not None:
        fin.appreciation_zillow_pct = float(details.appreciation_decade_pct)

    if (fin.appreciation_source or "").strip() != "Manual":
        blended, source = appreciation_blender(
            fin.appreciation_fhfa_pct, fin.appreciation_zillow_pct
        )
        fin.appreciation_pct = float(blended)
        fin.appreciation_source = source

    apply_mortgage_rate_autofill(fin, rate_resolver=rate_resolver)
    apply_maintenance_autofill(
        fin, prop, details, maintenance_resolver=maintenance_resolver
    )
    apply_utilities_autofill(
        fin, prop, details, utilities_resolver=utilities_resolver
    )
