from app.core.finance import (
    effective_price,
    estimate_monthly_pmi,
    monthly_payment,
    summarize,
)
from app.core.property_service import parse_zillow_url


def test_parse_zillow_homedetails():
    url = (
        "https://www.zillow.com/homedetails/"
        "123-Main-St-Seattle-WA-98101/98765432_zpid/"
    )
    parsed = parse_zillow_url(url)
    assert parsed["zpid"] == "98765432"
    assert "123 Main St Seattle WA 98101" == parsed["address_guess"]
    assert str(parsed["url"]).startswith("https://")


def test_parse_requires_zillow_host():
    try:
        parse_zillow_url("https://example.com/home/1")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_monthly_payment_zero_rate():
    assert abs(monthly_payment(120_000, 0, 10) - 1000.0) < 0.01


def test_summarize_cash_to_close():
    result = summarize(
        purchase_price=500_000,
        down_payment_pct=20,
        interest_rate_pct=6.0,
        loan_term_years=30,
        annual_property_tax=6_000,
        annual_insurance=1_200,
        monthly_hoa=50,
        closing_cost_pct=3.0,
    )
    assert result.down_payment == 100_000
    assert result.closing_costs == 15_000
    assert result.cash_to_close == 115_000
    assert result.loan_amount == 400_000
    assert result.monthly_total > result.monthly_principal_interest
    assert result.monthly_pmi == 0


def test_effective_price_prefers_offer():
    assert effective_price(500_000, 480_000) == 480_000
    assert effective_price(500_000, 0) == 500_000
    assert effective_price(500_000) == 500_000


def test_summarize_uses_offer_over_list():
    at_list = summarize(
        list_price=500_000,
        offer_price=0,
        down_payment_pct=20,
        interest_rate_pct=6.0,
        loan_term_years=30,
        annual_property_tax=6_000,
        annual_insurance=1_200,
        monthly_hoa=0,
        closing_cost_pct=3.0,
    )
    under_ask = summarize(
        list_price=500_000,
        offer_price=450_000,
        down_payment_pct=20,
        interest_rate_pct=6.0,
        loan_term_years=30,
        annual_property_tax=6_000,
        annual_insurance=1_200,
        monthly_hoa=0,
        closing_cost_pct=3.0,
    )
    assert at_list.effective_price == 500_000
    assert at_list.loan_amount == 400_000
    assert under_ask.effective_price == 450_000
    assert under_ask.loan_amount == 360_000
    assert under_ask.cash_to_close < at_list.cash_to_close
    assert under_ask.monthly_principal_interest < at_list.monthly_principal_interest


def test_estimate_monthly_pmi():
    assert estimate_monthly_pmi(400_000, 20) == 0
    assert estimate_monthly_pmi(400_000, 25) == 0
    # 0.5% of 400k / 12
    assert abs(estimate_monthly_pmi(400_000, 10) - (400_000 * 0.005 / 12)) < 0.01


def test_summarize_includes_pmi_under_20_down():
    with_pmi = summarize(
        list_price=500_000,
        offer_price=500_000,
        down_payment_pct=10,
        interest_rate_pct=6.0,
        loan_term_years=30,
        annual_property_tax=0,
        annual_insurance=0,
        monthly_hoa=0,
        closing_cost_pct=0,
    )
    no_pmi = summarize(
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
    assert with_pmi.monthly_pmi > 0
    assert no_pmi.monthly_pmi == 0
    assert with_pmi.monthly_total == with_pmi.monthly_principal_interest + with_pmi.monthly_pmi
