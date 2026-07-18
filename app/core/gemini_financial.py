from __future__ import annotations

import os
from typing import Mapping

from dotenv import load_dotenv

from app.core.finance import MortgageSummary

load_dotenv()

DEFAULT_MODEL = "gemini-2.5-flash-lite"
FINANCIAL_PROMPT_VERSION = "fin_v1"


def _money(n: float) -> str:
    return f"${n:,.0f}"


def _money_exact(n: float) -> str:
    return f"${n:,.2f}"


def _fmt_num(n: float | int) -> str:
    if isinstance(n, float) and n == int(n):
        return str(int(n))
    return str(n)


def build_financial_fingerprint(
    *,
    list_price: float = 0.0,
    offer_price: float = 0.0,
    down_payment_pct: float = 20.0,
    interest_rate_pct: float = 6.5,
    loan_term_years: int = 30,
    annual_property_tax: float = 0.0,
    annual_insurance: float = 0.0,
    monthly_hoa: float = 0.0,
    closing_cost_pct: float = 0.0,
) -> str:
    """Cache key: prompt version + round-trip-stable assumption fields."""
    parts = [
        FINANCIAL_PROMPT_VERSION,
        _fmt_num(float(list_price or 0)),
        _fmt_num(float(offer_price or 0)),
        _fmt_num(float(down_payment_pct or 0)),
        _fmt_num(float(interest_rate_pct or 0)),
        _fmt_num(int(loan_term_years or 30)),
        _fmt_num(float(annual_property_tax or 0)),
        _fmt_num(float(annual_insurance or 0)),
        _fmt_num(float(monthly_hoa or 0)),
        _fmt_num(float(closing_cost_pct or 0)),
    ]
    return "|".join(parts)


def build_financial_prompt(
    *,
    address: str,
    home_type: str,
    beds: float | None,
    baths: float | None,
    sqft: float | None,
    listing_hoa: float | None,
    summary: MortgageSummary,
    assumptions: Mapping[str, float | int],
) -> str:
    """Build a prompt that feeds calculator outputs — Gemini must not invent prices."""
    list_price = float(assumptions.get("list_price") or 0)
    offer_price = float(assumptions.get("offer_price") or 0)
    down_pct = float(assumptions.get("down_payment_pct") or 0)
    rate = float(assumptions.get("interest_rate_pct") or 0)
    term = int(assumptions.get("loan_term_years") or 30)
    annual_tax = float(assumptions.get("annual_property_tax") or 0)
    annual_ins = float(assumptions.get("annual_insurance") or 0)
    monthly_hoa = float(assumptions.get("monthly_hoa") or 0)
    closing_pct = float(assumptions.get("closing_cost_pct") or 0)

    listing_bits: list[str] = []
    if (home_type or "").strip():
        listing_bits.append(f"type={home_type.strip()}")
    if beds is not None:
        listing_bits.append(f"beds={beds:g}")
    if baths is not None:
        listing_bits.append(f"baths={baths:g}")
    if sqft is not None:
        listing_bits.append(f"sqft={sqft:g}")
    if listing_hoa is not None:
        listing_bits.append(f"listing HOA/mo={_money(float(listing_hoa))}")
    listing_line = ", ".join(listing_bits) if listing_bits else "details limited"

    offer_line = (
        f"Offer price: {_money(offer_price)}"
        if offer_price > 0
        else "Offer price: (not set — mortgage uses list)"
    )

    pmi_line = (
        f"PMI: {_money_exact(summary.monthly_pmi)}/mo"
        if summary.monthly_pmi > 0
        else "PMI: $0.00/mo (down ≥ 20% or no loan)"
    )

    return (
        "You are helping a homebuyer review the finances of a specific listing. "
        "Use ONLY the numbers provided below — do not invent or substitute prices, "
        "taxes, insurance, HOA, rates, or payment amounts. If something is zero or "
        "missing, say so rather than guessing.\n\n"
        f"Property: {(address or '').strip() or 'Unknown address'}\n"
        f"Listing context: {listing_line}\n\n"
        "Buyer assumptions (inputs):\n"
        f"- List price: {_money(list_price)}\n"
        f"- {offer_line}\n"
        f"- Price used for mortgage (effective): {_money(summary.effective_price)}\n"
        f"- Down payment: {down_pct:g}% → {_money(summary.down_payment)}\n"
        f"- Interest rate: {rate:g}%\n"
        f"- Loan term: {term} years\n"
        f"- Loan amount: {_money(summary.loan_amount)}\n"
        f"- Closing costs: {closing_pct:g}% → {_money(summary.closing_costs)}\n"
        f"- Cash to close (down + closing): {_money(summary.cash_to_close)}\n"
        f"- Annual property tax assumption: {_money(annual_tax)}\n"
        f"- Annual insurance assumption: {_money(annual_ins)}\n"
        f"- Monthly HOA assumption: {_money(monthly_hoa)}\n\n"
        "Calculated monthly housing cost (source of truth from our PITI calculator):\n"
        f"- Principal & interest (P&I): {_money_exact(summary.monthly_principal_interest)}\n"
        f"- Property tax: {_money_exact(summary.monthly_tax)}\n"
        f"- Insurance: {_money_exact(summary.monthly_insurance)}\n"
        f"- HOA: {_money_exact(summary.monthly_hoa)}\n"
        f"- {pmi_line}\n"
        f"- Total monthly (PITI+HOA+PMI): {_money_exact(summary.monthly_total)}\n"
        f"- Estimated total interest over the loan: {_money(summary.total_interest)}\n\n"
        "Write your response in markdown with exactly two sections:\n\n"
        "## Breakdown\n"
        "A short restatement of the key numbers (price basis, cash to close, monthly "
        "total and its main components). Keep it factual and brief.\n\n"
        "## Opinion\n"
        "A candid buy-side opinion: affordability flags, risks (tax/insurance/HOA "
        "assumptions, PMI, interest burden), and what to verify before offering. "
        "Be practical and balanced — not salesy. Optionally end with a short bullet "
        "list of 3–5 things to double-check.\n\n"
        "This is an AI opinion for research only, not financial advice. "
        "Do not invent comps or claim local tax rates you were not given."
    )


def _call_gemini(prompt: str) -> str:
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not set. Add it to your .env file and restart the app."
        )

    model = (os.getenv("GEMINI_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL

    try:
        from google import genai
    except ImportError as exc:
        raise ValueError("google-genai is not installed. Run: pip install google-genai") from exc

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model=model, contents=prompt)
    text = (getattr(response, "text", None) or "").strip()
    if not text:
        raise ValueError("Gemini returned an empty response.")
    return text


def generate_financial_commentary(
    *,
    address: str,
    home_type: str = "",
    beds: float | None = None,
    baths: float | None = None,
    sqft: float | None = None,
    listing_hoa: float | None = None,
    summary: MortgageSummary,
    assumptions: Mapping[str, float | int],
) -> str:
    """Call Gemini with calculator outputs; return breakdown + opinion markdown."""
    list_price = float(assumptions.get("list_price") or 0)
    offer_price = float(assumptions.get("offer_price") or 0)
    if list_price <= 0 and offer_price <= 0:
        raise ValueError("Set a list or offer price before asking Gemini about finances.")

    prompt = build_financial_prompt(
        address=address,
        home_type=home_type,
        beds=beds,
        baths=baths,
        sqft=sqft,
        listing_hoa=listing_hoa,
        summary=summary,
        assumptions=assumptions,
    )
    return _call_gemini(prompt)
