from app.core.home_insurance import resolve_annual_insurance


def test_prefers_zillow_insurance():
    amount, source = resolve_annual_insurance(
        annual_insurance=2_400,
        list_price=1_000_000,
        state="CA",
    )
    assert amount == 2_400
    assert source == "Zillow"


def test_scales_state_average_premium():
    # CA entry in table: avg_premium_usd=2011, reference=300000
    # → 2011 * (600000/300000) = 4022
    amount, source = resolve_annual_insurance(
        annual_insurance=None,
        list_price=600_000,
        state="CA",
    )
    assert amount == 4022
    assert "CA" in source


def test_unknown_state_unresolved():
    amount, source = resolve_annual_insurance(
        annual_insurance=None,
        list_price=600_000,
        state="XX",
    )
    assert amount is None
    assert source == ""


def test_missing_price_unresolved():
    amount, source = resolve_annual_insurance(
        annual_insurance=None,
        list_price=0,
        state="CA",
    )
    assert amount is None
    assert source == ""
