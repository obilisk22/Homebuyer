from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MortgageSummary:
    effective_price: float
    list_price: float
    offer_price: float
    loan_amount: float
    monthly_principal_interest: float
    monthly_tax: float
    monthly_insurance: float
    monthly_hoa: float
    monthly_pmi: float
    monthly_total: float
    down_payment: float
    closing_costs: float
    cash_to_close: float
    total_interest: float
    schedule: list[dict[str, float | int]]


def effective_price(list_price: float, offer_price: float = 0.0) -> float:
    """Price used for mortgage and cash-to-close: offer when set, else list."""
    if offer_price and offer_price > 0:
        return float(offer_price)
    return max(0.0, float(list_price or 0))


def estimate_monthly_pmi(loan_amount: float, down_payment_pct: float) -> float:
    """Rough PMI: 0.5% of loan / year when down payment is under 20%."""
    if loan_amount <= 0 or down_payment_pct >= 20.0:
        return 0.0
    return (loan_amount * 0.005) / 12.0


def monthly_payment(principal: float, annual_rate_pct: float, years: int) -> float:
    if principal <= 0:
        return 0.0
    n = max(years, 1) * 12
    r = (annual_rate_pct / 100.0) / 12.0
    if r == 0:
        return principal / n
    return principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)


def amortization_schedule(
    principal: float, annual_rate_pct: float, years: int
) -> list[dict[str, float | int]]:
    payment = monthly_payment(principal, annual_rate_pct, years)
    balance = principal
    r = (annual_rate_pct / 100.0) / 12.0
    n = max(years, 1) * 12
    rows: list[dict[str, float | int]] = []
    for month in range(1, n + 1):
        interest = balance * r
        principal_paid = payment - interest
        if month == n:
            principal_paid = balance
            payment_this = interest + principal_paid
        else:
            payment_this = payment
        balance = max(0.0, balance - principal_paid)
        rows.append(
            {
                "month": month,
                "payment": round(payment_this, 2),
                "principal": round(principal_paid, 2),
                "interest": round(interest, 2),
                "balance": round(balance, 2),
            }
        )
        if balance <= 0:
            break
    return rows


def summarize(
    list_price: float = 0.0,
    offer_price: float = 0.0,
    down_payment_pct: float = 20.0,
    interest_rate_pct: float = 6.5,
    loan_term_years: int = 30,
    annual_property_tax: float = 0.0,
    annual_insurance: float = 0.0,
    monthly_hoa: float = 0.0,
    closing_cost_pct: float = 0.0,
    *,
    purchase_price: float | None = None,
) -> MortgageSummary:
    """Build a mortgage / PITI summary.

    ``purchase_price`` is a legacy alias: when provided and list/offer are unset,
    both are treated as that price (tests and older callers).
    """
    if purchase_price is not None and not list_price and not offer_price:
        list_price = purchase_price
        offer_price = purchase_price

    price = effective_price(list_price, offer_price)
    down = price * (down_payment_pct / 100.0)
    loan = max(0.0, price - down)
    pi = monthly_payment(loan, interest_rate_pct, loan_term_years)
    tax = annual_property_tax / 12.0
    ins = annual_insurance / 12.0
    pmi = estimate_monthly_pmi(loan, down_payment_pct)
    closing = price * (closing_cost_pct / 100.0)
    schedule = amortization_schedule(loan, interest_rate_pct, loan_term_years)
    total_interest = sum(float(row["interest"]) for row in schedule)
    return MortgageSummary(
        effective_price=price,
        list_price=float(list_price or 0),
        offer_price=float(offer_price or 0),
        loan_amount=loan,
        monthly_principal_interest=pi,
        monthly_tax=tax,
        monthly_insurance=ins,
        monthly_hoa=monthly_hoa,
        monthly_pmi=pmi,
        monthly_total=pi + tax + ins + monthly_hoa + pmi,
        down_payment=down,
        closing_costs=closing,
        cash_to_close=down + closing,
        total_interest=total_interest,
        schedule=schedule,
    )
