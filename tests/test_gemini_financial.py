from app.core.finance import summarize
from app.core.gemini_financial import (
    FINANCIAL_PROMPT_VERSION,
    build_financial_fingerprint,
    build_financial_prompt,
)


def _sample_assumptions() -> dict:
    return {
        "list_price": 900_000.0,
        "offer_price": 875_000.0,
        "down_payment_pct": 20.0,
        "interest_rate_pct": 6.5,
        "loan_term_years": 30,
        "annual_property_tax": 9_000.0,
        "annual_insurance": 2_400.0,
        "monthly_hoa": 350.0,
        "closing_cost_pct": 3.0,
    }


def test_fingerprint_includes_version_and_key_assumptions():
    fp = build_financial_fingerprint(**_sample_assumptions())
    assert fp.startswith(f"{FINANCIAL_PROMPT_VERSION}|")
    assert "900000" in fp or "900000.0" in fp
    assert "875000" in fp or "875000.0" in fp
    assert "20" in fp
    assert "6.5" in fp


def test_fingerprint_changes_when_rate_changes():
    base = _sample_assumptions()
    a = build_financial_fingerprint(**base)
    base["interest_rate_pct"] = 7.0
    b = build_financial_fingerprint(**base)
    assert a != b


def test_fingerprint_stable_for_same_inputs():
    a = build_financial_fingerprint(**_sample_assumptions())
    b = build_financial_fingerprint(**_sample_assumptions())
    assert a == b


def test_prompt_restates_calculator_numbers():
    data = _sample_assumptions()
    summary = summarize(**data)
    prompt = build_financial_prompt(
        address="123 Main St, Los Angeles, CA",
        home_type="Condo",
        beds=2,
        baths=2,
        sqft=1100,
        listing_hoa=350,
        summary=summary,
        assumptions=data,
    )
    lower = prompt.lower()
    assert "875000" in prompt.replace(",", "") or "875,000" in prompt
    assert "ai" in lower or "opinion" in lower
    assert "breakdown" in lower
    assert str(round(summary.monthly_total, 2)) in prompt or f"${summary.monthly_total:,.0f}" in prompt
    assert "p&i" in lower or "principal" in lower
    assert "hoa" in lower
    assert "not invent" in lower or "do not invent" in lower or "don't invent" in lower


def test_prompt_uses_list_when_offer_unset():
    data = _sample_assumptions()
    data["offer_price"] = 0.0
    summary = summarize(**data)
    prompt = build_financial_prompt(
        address="456 Oak Ave",
        home_type="Single Family",
        beds=3,
        baths=2,
        sqft=1800,
        listing_hoa=None,
        summary=summary,
        assumptions=data,
    )
    assert "900" in prompt.replace(",", "")
    assert summary.effective_price == 900_000.0
