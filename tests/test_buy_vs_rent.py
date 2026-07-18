from app.core.finance import (
    blend_appreciation_rates,
    buy_vs_rent_projection,
    summarize,
)
from openpyxl import Workbook

from app.core.fhfa_hpi import _series_from_worksheet, cagr_from_index_series


def test_blend_both_sources():
    rate, src = blend_appreciation_rates(4.0, 6.0)
    assert rate == 5.0
    assert src == "FHFA+Zillow"


def test_blend_fhfa_only():
    rate, src = blend_appreciation_rates(4.0, None)
    assert rate == 4.0
    assert src == "FHFA"


def test_blend_zillow_only():
    rate, src = blend_appreciation_rates(None, 6.0)
    assert rate == 6.0
    assert src == "Zillow"


def test_blend_default():
    rate, src = blend_appreciation_rates(None, None)
    assert rate == 3.0
    assert src == "Default"


def test_buy_vs_rent_year_zero():
    summary = summarize(
        list_price=500_000,
        offer_price=500_000,
        down_payment_pct=20,
        interest_rate_pct=6.0,
        loan_term_years=30,
        annual_property_tax=0,
        annual_insurance=0,
        monthly_hoa=0,
        closing_cost_pct=0,
    )
    rows = buy_vs_rent_projection(
        summary=summary,
        appreciation_pct=0.0,
        monthly_rent=summary.monthly_total,
        invest_return_pct=10.0,
        selling_cost_pct=6.0,
    )
    assert rows[0].year == 0
    # Buy: 500k - 400k - 6%*500k = 70_000
    assert abs(rows[0].buy_net_worth - 70_000) < 1.0
    # Rent portfolio starts at cash_to_close = 100_000
    assert abs(rows[0].rent_invest_net_worth - 100_000) < 1.0
    assert len(rows) == 31  # years 0..30


def test_buy_vs_rent_invests_surplus_when_rent_below_piti():
    summary = summarize(
        list_price=500_000,
        offer_price=500_000,
        down_payment_pct=20,
        interest_rate_pct=0.0,
        loan_term_years=30,
        annual_property_tax=0,
        annual_insurance=0,
        monthly_hoa=0,
        closing_cost_pct=0,
    )
    # Zero rate → P&I = 400_000 / 360; rent half of that → positive monthly invest
    rent = summary.monthly_total / 2.0
    rows = buy_vs_rent_projection(
        summary=summary,
        appreciation_pct=0.0,
        monthly_rent=rent,
        invest_return_pct=0.0,  # isolate contribution sum
        selling_cost_pct=6.0,
    )
    # After 12 months with 0% return: start 100k + 12 * (piti - rent)
    expected = 100_000 + 12 * (summary.monthly_total - rent)
    assert abs(rows[1].rent_invest_net_worth - expected) < 1.0


def test_buy_vs_rent_no_negative_contribution():
    summary = summarize(
        list_price=500_000,
        offer_price=500_000,
        down_payment_pct=20,
        interest_rate_pct=6.0,
        loan_term_years=30,
        annual_property_tax=0,
        annual_insurance=0,
        monthly_hoa=0,
        closing_cost_pct=0,
    )
    rows = buy_vs_rent_projection(
        summary=summary,
        appreciation_pct=0.0,
        monthly_rent=summary.monthly_total + 5_000,
        invest_return_pct=0.0,
        selling_cost_pct=6.0,
    )
    # Portfolio stays at cash_to_close when rent > PITI and 0% return
    assert abs(rows[5].rent_invest_net_worth - 100_000) < 1.0


def test_cagr_from_index_series_decade():
    # index doubles over 10 years → CAGR = 2**(1/10) - 1 ≈ 7.177%
    points = [(2014, 100.0), (2024, 200.0)]
    rate = cagr_from_index_series(points, span_years=10)
    assert rate is not None
    assert abs(rate - (((200 / 100) ** (1 / 10) - 1) * 100)) < 0.01


def test_cagr_insufficient_history():
    assert cagr_from_index_series([(2024, 100.0)], span_years=10) is None


def test_fhfa_series_skips_title_rows_and_uses_hpi_level():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["FHFA House Price Index: ZIP Codes"])
    sheet.append(["Notes: Annual Change is not the HPI level."])
    sheet.append([])
    sheet.append(
        [
            "Five-Digit ZIP Code",
            "Year",
            "Annual Change (%)",
            "HPI",
            "HPI with 1990 base",
        ]
    )
    sheet.append(["98116", 2014, 1.0, 100.0, 90.0])
    sheet.append(["98116", 2024, 2.0, 200.0, 180.0])

    points = _series_from_worksheet(sheet, "98116")

    assert points == [(2014, 100.0), (2024, 200.0)]
    rate = cagr_from_index_series(points)
    assert rate is not None
    assert abs(rate - (((200 / 100) ** (1 / 10) - 1) * 100)) < 0.01
