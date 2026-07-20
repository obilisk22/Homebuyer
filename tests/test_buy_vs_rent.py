from app.core.finance import (
    blend_appreciation_rates,
    buy_vs_rent_projection,
    capital_gains_tax,
    interest_in_loan_year,
    rent_cagr_pct,
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
        monthly_budget=13_000,
        marginal_tax_pct=0,
        cg_tax_pct=24,
        cg_exclusion=500_000,
    )
    assert rows[0].year == 0
    # Buy: amount_realized 470k - loan 400k - cg 0 + portfolio 0 = 70_000
    assert abs(rows[0].buy_net_worth - 70_000) < 1.0
    assert abs(rows[0].rent_invest_net_worth - 100_000) < 1.0
    assert len(rows) == 31


def test_two_way_surplus_both_invest_when_under_budget():
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
    rent = summary.monthly_total / 2.0
    budget = 5_000.0
    rows = buy_vs_rent_projection(
        summary=summary,
        appreciation_pct=0.0,
        monthly_rent=rent,
        invest_return_pct=0.0,
        selling_cost_pct=6.0,
        monthly_budget=budget,
        marginal_tax_pct=0,
        cg_exclusion=500_000,
    )
    buy_contrib = budget - summary.monthly_total
    rent_contrib = budget - rent
    # Buy: liquid equity at Y1 + 12 * buy_contrib
    # home still 500k, bal after 12 mo at 0% rate: 400k - 12*(400k/360)
    bal_y1 = 400_000 - 12 * (400_000 / 360)
    buy_liquid = 500_000 * 0.94 - bal_y1
    expected_buy = buy_liquid + 12 * buy_contrib
    expected_rent = 100_000 + 12 * rent_contrib
    assert abs(rows[1].buy_net_worth - expected_buy) < 1.0
    assert abs(rows[1].rent_invest_net_worth - expected_rent) < 1.0


def test_no_invest_when_cost_exceeds_budget():
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
    rows = buy_vs_rent_projection(
        summary=summary,
        appreciation_pct=0.0,
        monthly_rent=summary.monthly_total + 5_000,
        invest_return_pct=0.0,
        selling_cost_pct=6.0,
        monthly_budget=100.0,  # below both costs
        marginal_tax_pct=0,
        cg_exclusion=500_000,
    )
    assert abs(rows[5].rent_invest_net_worth - 100_000) < 1.0


def test_tax_shield_raises_buy_surplus():
    """Interest + property tax shield lowers after-tax owner cost → more buy invest."""
    summary = summarize(
        list_price=500_000,
        offer_price=500_000,
        down_payment_pct=20,
        interest_rate_pct=6.0,
        loan_term_years=30,
        annual_property_tax=12_000,
        annual_insurance=0,
        monthly_hoa=0,
        closing_cost_pct=0,
    )
    rent = summary.monthly_total
    common = dict(
        summary=summary,
        appreciation_pct=0.0,
        monthly_rent=rent,
        invest_return_pct=0.0,
        selling_cost_pct=6.0,
        monthly_budget=13_000,
        cg_exclusion=500_000,
        salt_cap=10_000,
    )
    no_tax = buy_vs_rent_projection(**common, marginal_tax_pct=0)
    with_tax = buy_vs_rent_projection(**common, marginal_tax_pct=41)
    # With shield, buyer invests more → higher buy NW at Y1
    assert with_tax[1].buy_net_worth > no_tax[1].buy_net_worth


def test_capital_gains_tax_helper():
    assert capital_gains_tax(
        amount_realized=600_000, cost_basis=500_000, exclusion=500_000, cg_rate_pct=24
    ) == 0.0
    # gain 400k, exclusion 250k → taxable 150k * 24% = 36k
    assert (
        capital_gains_tax(
            amount_realized=900_000,
            cost_basis=500_000,
            exclusion=250_000,
            cg_rate_pct=24,
        )
        == 36_000.0
    )


def test_cg_tax_reduces_buy_nw_when_gain_exceeds_exclusion():
    summary = summarize(
        list_price=400_000,
        offer_price=400_000,
        down_payment_pct=20,
        interest_rate_pct=0.0,
        loan_term_years=30,
        annual_property_tax=0,
        annual_insurance=0,
        monthly_hoa=0,
        closing_cost_pct=0,
    )
    # High appreciation so gain exceeds small exclusion
    rows = buy_vs_rent_projection(
        summary=summary,
        appreciation_pct=20.0,
        monthly_rent=summary.monthly_total,
        invest_return_pct=0.0,
        selling_cost_pct=0.0,
        monthly_budget=0.0,
        marginal_tax_pct=0,
        cg_tax_pct=20.0,
        cg_exclusion=50_000.0,
    )
    # Y5 home = 400k * 1.2^5; amount_realized = home; gain = home - 400k
    home5 = 400_000 * (1.2**5)
    gain = home5 - 400_000
    taxable = gain - 50_000
    cg = taxable * 0.20
    bal5 = rows[5].loan_balance
    expected = home5 - bal5 - cg
    assert abs(rows[5].buy_net_worth - expected) < 2.0


def test_cagr_from_index_series_decade():
    points = [(2014, 100.0), (2024, 200.0)]
    rate = cagr_from_index_series(points, span_years=10)
    assert rate is not None
    assert abs(rate - (((200 / 100) ** (1 / 10) - 1) * 100)) < 0.01


def test_cagr_insufficient_history():
    assert cagr_from_index_series([(2024, 100.0)], span_years=10) is None


def test_rent_cagr_pct_five_years():
    rate = rent_cagr_pct(1000.0, 2000.0, years=5)
    assert rate is not None
    assert abs(rate - ((2.0 ** (1 / 5) - 1.0) * 100.0)) < 0.01


def test_rent_cagr_pct_invalid():
    assert rent_cagr_pct(0, 2000.0) is None
    assert rent_cagr_pct(1000.0, 0) is None
    assert rent_cagr_pct(-1, 2000) is None


def test_buy_vs_rent_applies_rent_growth_year_one():
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
    rent0 = 1_000.0
    budget = 3_000.0
    rows = buy_vs_rent_projection(
        summary=summary,
        appreciation_pct=0.0,
        monthly_rent=rent0,
        invest_return_pct=0.0,
        selling_cost_pct=6.0,
        rent_growth_pct=10.0,
        monthly_budget=budget,
        marginal_tax_pct=0,
        cg_exclusion=500_000,
    )
    rent_y1 = rent0 * 1.10
    rent_contrib = budget - rent_y1
    expected = 100_000 + 12 * rent_contrib
    assert abs(rows[1].rent_invest_net_worth - expected) < 1.0


def test_buy_vs_rent_inflates_maint_and_utils_with_rent_growth():
    """Maint/utils grow like rent: year-0→1 uses (1+g)^1; PITI stays flat."""
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
    piti = float(summary.monthly_total)
    maint0 = 100.0
    utils0 = 50.0
    g = 0.10
    budget = 5_000.0
    # Rent equals owner year-1 cash so rent surplus stays out of the buy NW check.
    rent_y1 = piti + maint0 * (1.0 + g) + utils0 * (1.0 + g)
    rows = buy_vs_rent_projection(
        summary=summary,
        appreciation_pct=0.0,
        monthly_rent=rent_y1 / (1.0 + g),
        invest_return_pct=0.0,
        selling_cost_pct=6.0,
        rent_growth_pct=10.0,
        monthly_maintenance=maint0,
        monthly_utilities=utils0,
        monthly_budget=budget,
        marginal_tax_pct=0,
        cg_exclusion=500_000,
    )
    owner_y1 = piti + maint0 * (1.0 + g) + utils0 * (1.0 + g)
    buy_contrib = budget - owner_y1
    buy_portfolio = 12 * buy_contrib
    # Year 1: home flat, sell 6%, loan after 12 zero-interest payments, + portfolio.
    home = 500_000.0
    bal = float(summary.schedule[11]["balance"])
    amount_realized = home * 0.94
    expected_buy_nw = amount_realized - bal + buy_portfolio
    assert abs(rows[1].buy_net_worth - expected_buy_nw) < 1.0
    # Flat maint/utils would leave a larger surplus → higher buy NW.
    flat_owner = piti + maint0 + utils0
    flat_portfolio = 12 * (budget - flat_owner)
    flat_buy_nw = amount_realized - bal + flat_portfolio
    assert rows[1].buy_net_worth < flat_buy_nw - 1.0


def test_buy_vs_rent_maint_utils_inflate_year_two():
    """Year-1→2 contributions use (1+g)^2 for maint/utils (same timing as rent)."""
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
    piti = float(summary.monthly_total)
    maint0 = 200.0
    utils0 = 80.0
    g = 0.05
    budget = 8_000.0
    rows = buy_vs_rent_projection(
        summary=summary,
        appreciation_pct=0.0,
        monthly_rent=piti,
        invest_return_pct=0.0,
        selling_cost_pct=6.0,
        rent_growth_pct=5.0,
        monthly_maintenance=maint0,
        monthly_utilities=utils0,
        monthly_budget=budget,
        marginal_tax_pct=0,
        cg_exclusion=500_000,
    )
    buy_port = 0.0
    for year in (0, 1):
        opex = (maint0 + utils0) * ((1.0 + g) ** (year + 1))
        buy_port += 12 * (budget - (piti + opex))
    home = 500_000.0
    bal = float(summary.schedule[23]["balance"])
    expected = home * 0.94 - bal + buy_port
    assert abs(rows[2].buy_net_worth - expected) < 1.0


def test_buy_vs_rent_custom_selling_cost():
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
        selling_cost_pct=10.0,
        monthly_budget=13_000,
        marginal_tax_pct=0,
        cg_exclusion=500_000,
    )
    assert abs(rows[0].buy_net_worth - 50_000) < 1.0


def test_buy_vs_rent_custom_invest_return_compounds():
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
    # Budget equals owner cost and rent → no monthly contrib; rent portfolio compounds seed
    piti = summary.monthly_total
    rows = buy_vs_rent_projection(
        summary=summary,
        appreciation_pct=0.0,
        monthly_rent=piti,
        invest_return_pct=12.0,
        selling_cost_pct=6.0,
        monthly_budget=piti,
        marginal_tax_pct=0,
        cg_exclusion=500_000,
    )
    r_month = 0.12 / 12.0
    expected = 100_000 * ((1.0 + r_month) ** 12)
    assert abs(rows[1].rent_invest_net_worth - expected) < 1.0


def test_interest_in_loan_year_sums_first_twelve_months():
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
    total = interest_in_loan_year(summary.schedule, 0)
    manual = sum(float(r["interest"]) for r in summary.schedule if int(r["month"]) <= 12)
    assert abs(total - manual) < 0.01


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
