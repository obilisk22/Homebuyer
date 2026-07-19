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
    monthly_maintenance: float = 0.0

    @property
    def monthly_owner_total(self) -> float:
        """PITI + maintenance (ownership cash cost for display)."""
        return float(self.monthly_total) + float(self.monthly_maintenance or 0)


def effective_price(list_price: float, offer_price: float = 0.0) -> float:
    """Price used for mortgage and cash-to-close: offer when set, else list."""
    if offer_price and offer_price > 0:
        return float(offer_price)
    return max(0.0, float(list_price or 0))


def down_payment_dollars(price: float, down_payment_pct: float) -> float:
    """Convert a down-payment percent of ``price`` into dollars."""
    if price <= 0:
        return 0.0
    return float(price) * (float(down_payment_pct or 0) / 100.0)


def down_payment_pct_from_dollars(price: float, down_payment_dollars_amt: float) -> float:
    """Convert a down-payment dollar amount into a percent of ``price``."""
    if price <= 0:
        return 0.0
    return (float(down_payment_dollars_amt or 0) / float(price)) * 100.0


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
    monthly_maintenance: float = 0.0,
) -> MortgageSummary:
    """Build a mortgage / PITI summary.

    ``purchase_price`` is a legacy alias: when provided and list/offer are unset,
    both are treated as that price (tests and older callers).
    ``monthly_maintenance`` is tracked for ownership display; ``monthly_total``
    remains PITI-only so buy-vs-rent can add maintenance once.
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
        monthly_maintenance=float(monthly_maintenance or 0),
    )


@dataclass(frozen=True)
class BuyVsRentYear:
    year: int
    buy_net_worth: float
    rent_invest_net_worth: float
    home_value: float
    loan_balance: float


def blend_appreciation_rates(
    fhfa_pct: float | None,
    zillow_pct: float | None,
    *,
    default: float = 3.0,
) -> tuple[float, str]:
    rates: list[float] = []
    if fhfa_pct is not None:
        rates.append(float(fhfa_pct))
    if zillow_pct is not None:
        rates.append(float(zillow_pct))
    if not rates:
        return float(default), "Default"
    blended = sum(rates) / len(rates)
    if fhfa_pct is not None and zillow_pct is not None:
        return blended, "FHFA+Zillow"
    if fhfa_pct is not None:
        return blended, "FHFA"
    return blended, "Zillow"


def rent_cagr_pct(
    rent_start: float, rent_end: float, *, years: int = 5
) -> float | None:
    if years <= 0:
        return None
    try:
        start = float(rent_start)
        end = float(rent_end)
    except (TypeError, ValueError):
        return None
    if start <= 0 or end <= 0:
        return None
    return ((end / start) ** (1.0 / years) - 1.0) * 100.0


def interest_in_loan_year(
    schedule: list[dict[str, float | int]], year_index: int
) -> float:
    """Sum mortgage interest for loan year ``year_index`` (0 → months 1–12)."""
    start = int(year_index) * 12 + 1
    end = start + 12
    total = 0.0
    for row in schedule:
        month = int(row["month"])
        if start <= month < end:
            total += float(row["interest"])
    return total


def capital_gains_tax(
    *,
    amount_realized: float,
    cost_basis: float,
    exclusion: float,
    cg_rate_pct: float,
) -> float:
    """Tax on primary-residence gain after exclusion (0 if loss or fully excluded)."""
    gain = float(amount_realized) - float(cost_basis)
    taxable = max(0.0, gain - max(0.0, float(exclusion)))
    return taxable * (float(cg_rate_pct) / 100.0)


def buy_vs_rent_projection(
    *,
    summary: MortgageSummary,
    appreciation_pct: float,
    monthly_rent: float,
    invest_return_pct: float = 10.0,
    selling_cost_pct: float = 6.0,
    rent_growth_pct: float = 0.0,
    monthly_maintenance: float = 0.0,
    monthly_budget: float = 13_000.0,
    marginal_tax_pct: float = 41.0,
    cg_tax_pct: float = 24.0,
    cg_exclusion: float = 500_000.0,
    salt_cap: float = 10_000.0,
    annual_property_tax: float | None = None,
) -> list[BuyVsRentYear]:
    """Project buy vs rent net worth with two-way budget surplus and tax effects.

    Both paths invest ``max(0, budget − housing_cost)``. Buyer housing cost is
    PITI + maintenance minus a simplified interest + SALT-capped property-tax
    shield. Buy NW includes the buyer investment portfolio and CG tax on a
    hypothetical sale each year (primary-residence exclusion applied).
    """
    term_years = max(len(summary.schedule) // 12, 0)

    price0 = float(summary.effective_price)
    loan0 = float(summary.loan_amount)
    sell = float(selling_cost_pct) / 100.0
    appr = float(appreciation_pct) / 100.0
    r_month = (float(invest_return_pct) / 100.0) / 12.0
    piti = float(summary.monthly_total)
    maint = float(monthly_maintenance or 0)
    g = float(rent_growth_pct or 0) / 100.0
    rent0 = float(monthly_rent or 0)
    budget = float(monthly_budget or 0)
    marg = float(marginal_tax_pct or 0) / 100.0
    prop_tax = (
        float(annual_property_tax)
        if annual_property_tax is not None
        else float(summary.monthly_tax) * 12.0
    )
    prop_deduct = min(max(0.0, prop_tax), max(0.0, float(salt_cap)))

    bal_by_month = {int(row["month"]): float(row["balance"]) for row in summary.schedule}

    rent_portfolio = float(summary.cash_to_close)
    buy_portfolio = 0.0
    rows: list[BuyVsRentYear] = []

    for year in range(0, term_years + 1):
        home = price0 * ((1.0 + appr) ** year)
        if year == 0:
            bal = loan0
        else:
            bal = bal_by_month.get(year * 12, 0.0)
        amount_realized = home * (1.0 - sell)
        cg_tax = capital_gains_tax(
            amount_realized=amount_realized,
            cost_basis=price0,
            exclusion=float(cg_exclusion),
            cg_rate_pct=float(cg_tax_pct),
        )
        buy_nw = amount_realized - bal - cg_tax + buy_portfolio
        rows.append(
            BuyVsRentYear(
                year=year,
                buy_net_worth=round(buy_nw, 2),
                rent_invest_net_worth=round(rent_portfolio, 2),
                home_value=round(home, 2),
                loan_balance=round(bal, 2),
            )
        )
        if year == term_years:
            break

        interest_y = interest_in_loan_year(summary.schedule, year)
        shield_y = marg * (interest_y + prop_deduct)
        owner_after_tax = piti + maint - shield_y / 12.0
        # Rent for contributions after snapshot ``year`` (matches prior growth timing)
        rent_year = rent0 * ((1.0 + g) ** (year + 1))

        buy_contrib = max(0.0, budget - owner_after_tax)
        rent_contrib = max(0.0, budget - rent_year)
        for _ in range(12):
            buy_portfolio = buy_portfolio * (1.0 + r_month) + buy_contrib
            rent_portfolio = rent_portfolio * (1.0 + r_month) + rent_contrib

    return rows
