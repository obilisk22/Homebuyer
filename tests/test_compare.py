"""Side-by-side compare rows (TODO-018)."""

from __future__ import annotations

import pytest

from app.core.compare import build_compare_rows, parse_compare_ids
from app.core.library_export import snapshot_from_property
from app.core.models import FinancialAssumptions, Property


def _prop(
    prop_id: int,
    *,
    address: str,
    list_price: float,
    beds: float = 3,
    baths: float = 2,
    sqft: float = 1_000,
) -> Property:
    prop = Property(
        address=address,
        zillow_url=f"https://www.zillow.com/homedetails/{prop_id}_zpid/",
        list_price=list_price,
        beds=beds,
        baths=baths,
        sqft=sqft,
        city="Seattle",
        state="WA",
        zip_code="98101",
        financial=FinancialAssumptions(
            list_price=list_price,
            offer_price=0,
            down_payment_pct=20,
            interest_rate_pct=6.0,
            loan_term_years=30,
            annual_property_tax=list_price * 0.01,
            annual_insurance=1_200,
            monthly_hoa=0,
            closing_cost_pct=3.0,
        ),
    )
    prop.id = prop_id
    return prop


def test_parse_compare_ids_accepts_comma_and_hyphen():
    assert parse_compare_ids("3,1,2") == [3, 1, 2]
    assert parse_compare_ids("10-20-30") == [10, 20, 30]
    assert parse_compare_ids(" 4 , 5 ") == [4, 5]
    assert parse_compare_ids("") == []
    assert parse_compare_ids("1,abc,2") == [1, 2]


def test_build_compare_rows_requires_two_to_four():
    props = [_prop(1, address="1 A St", list_price=100_000)]
    with pytest.raises(ValueError, match="2–4"):
        build_compare_rows(props)

    props4 = [
        _prop(i, address=f"{i} St", list_price=100_000 * i) for i in range(1, 5)
    ]
    rows = build_compare_rows(props4)
    assert len(rows) == 4

    props5 = props4 + [_prop(5, address="5 St", list_price=500_000)]
    with pytest.raises(ValueError, match="2–4"):
        build_compare_rows(props5)


def test_build_compare_rows_includes_money_fields():
    a = _prop(1, address="100 Cheap St", list_price=300_000, sqft=1_500)
    b = _prop(2, address="200 Pricey St", list_price=600_000, sqft=2_000)
    rows = build_compare_rows([a, b])
    assert rows[0].address == "100 Cheap St"
    assert rows[0].list_price == 300_000
    assert rows[0].price_per_sqft == 200.0
    assert rows[0].beds == 3
    assert rows[0].baths == 2
    assert rows[0].monthly_piti is not None and rows[0].monthly_piti > 0
    assert rows[0].cash_to_close is not None and rows[0].cash_to_close > 0
    # Same shape as library snapshot math
    snap_b = snapshot_from_property(b)
    assert rows[1].monthly_piti == snap_b.monthly_piti
    assert rows[1].cash_to_close == snap_b.cash_to_close
