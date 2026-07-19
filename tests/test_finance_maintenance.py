from app.core.finance import summarize


def test_monthly_owner_total_includes_maintenance():
    result = summarize(
        list_price=500_000,
        offer_price=0,
        down_payment_pct=20,
        interest_rate_pct=0,
        loan_term_years=30,
        annual_property_tax=0,
        annual_insurance=0,
        monthly_hoa=0,
        closing_cost_pct=0,
        monthly_maintenance=250,
    )
    assert result.monthly_total == result.monthly_principal_interest
    assert result.monthly_owner_total == result.monthly_total + 250
    assert result.monthly_maintenance == 250
