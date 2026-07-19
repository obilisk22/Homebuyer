"""Tests for financial field help map and ownership total with utilities."""

from app.core.finance import summarize
from app.modules.financial import _FIELD_HELP


def test_field_help_covers_primary_and_advanced_keys():
    required = {
        "offer_price",
        "down_payment_dollars",
        "interest_rate_pct",
        "annual_property_tax",
        "monthly_maintenance",
        "monthly_utilities",
        "monthly_rent",
        "rent_control",
        "invest_return_pct",
        "monthly_budget",
        "marginal_tax_pct",
        "salt_cap",
    }
    assert required.issubset(_FIELD_HELP.keys())
    for key in required:
        assert len(_FIELD_HELP[key]) > 20


def test_monthly_owner_total_includes_utilities():
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
        monthly_utilities=180,
    )
    assert result.monthly_total == result.monthly_principal_interest
    assert result.monthly_utilities == 180
    assert result.monthly_owner_total == result.monthly_total + 250 + 180
