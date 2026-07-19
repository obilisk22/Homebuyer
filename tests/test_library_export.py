"""Library financial snapshots + CSV/JSON export (TODO-016)."""

from __future__ import annotations

import csv
import io
import json

from app.core.finance import summarize
from app.core.library_export import (
    export_library_csv,
    export_library_json,
    snapshot_from_property,
)
from app.core.models import FinancialAssumptions, Property


def _prop(
    *,
    address: str = "123 Main St, Seattle, WA 98101",
    list_price: float | None = 500_000,
    beds: float | None = 3,
    baths: float | None = 2,
    sqft: float | None = 1_250,
    financial: FinancialAssumptions | None = None,
) -> Property:
    prop = Property(
        address=address,
        zillow_url="https://www.zillow.com/homedetails/123-Main-St/1_zpid/",
        list_price=list_price,
        beds=beds,
        baths=baths,
        sqft=sqft,
        city="Seattle",
        state="WA",
        zip_code="98101",
    )
    prop.id = 7
    if financial is not None:
        prop.financial = financial
    return prop


def test_snapshot_without_financials_has_no_piti():
    snap = snapshot_from_property(_prop(financial=None))
    assert snap.has_financials is False
    assert snap.monthly_piti is None
    assert snap.cash_to_close is None
    assert snap.price_per_sqft == 400.0  # 500k / 1250


def test_snapshot_uses_finance_summarize_from_assumptions():
    fin = FinancialAssumptions(
        list_price=500_000,
        offer_price=480_000,
        down_payment_pct=20,
        interest_rate_pct=6.0,
        loan_term_years=30,
        annual_property_tax=6_000,
        annual_insurance=1_200,
        monthly_hoa=50,
        closing_cost_pct=3.0,
    )
    expected = summarize(
        list_price=500_000,
        offer_price=480_000,
        down_payment_pct=20,
        interest_rate_pct=6.0,
        loan_term_years=30,
        annual_property_tax=6_000,
        annual_insurance=1_200,
        monthly_hoa=50,
        closing_cost_pct=3.0,
    )
    snap = snapshot_from_property(_prop(financial=fin))
    assert snap.has_financials is True
    assert snap.offer_price == 480_000
    assert snap.effective_price == 480_000
    assert snap.monthly_piti == expected.monthly_total
    assert snap.cash_to_close == expected.cash_to_close
    assert snap.price_per_sqft == 500_000 / 1_250


def test_export_csv_and_json_include_financial_fields():
    fin = FinancialAssumptions(
        list_price=400_000,
        offer_price=0,
        down_payment_pct=20,
        interest_rate_pct=6.5,
        loan_term_years=30,
        annual_property_tax=4_800,
        annual_insurance=1_000,
        monthly_hoa=0,
        closing_cost_pct=3.0,
    )
    props = [_prop(financial=fin)]
    snaps = [snapshot_from_property(p) for p in props]

    csv_text = export_library_csv(snaps)
    reader = csv.DictReader(io.StringIO(csv_text))
    row = next(reader)
    assert row["address"].startswith("123 Main")
    assert row["list_price"] == "400000"
    assert "monthly_piti" in row
    assert float(row["monthly_piti"]) > 0
    assert float(row["cash_to_close"]) == 400_000 * 0.20 + 400_000 * 0.03

    payload = json.loads(export_library_json(snaps))
    assert isinstance(payload, list)
    assert payload[0]["id"] == 7
    assert payload[0]["monthly_piti"] == snaps[0].monthly_piti
    assert payload[0]["cash_to_close"] == snaps[0].cash_to_close
