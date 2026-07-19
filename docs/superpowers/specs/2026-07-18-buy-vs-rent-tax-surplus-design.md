# Buy vs rent: two-way surplus + tax shields (design)

**Date:** 2026-07-18  
**Status:** Approved (conversational)  
**Defaults profile:** CA married filing jointly

## Problem

The buy-vs-rent chart one-way invests only when ownership costs exceed rent, and ignores tax effects. That structurally favors rent+invest for CA homes. We need a shared monthly budget surplus on **both** paths, plus mortgage-interest / property-tax shields and primary-residence capital-gains tax on hypothetical sales.

## Locked decisions

1. **Monthly budget** default **$13,000** (editable). Both paths invest `max(0, budget − their_monthly_housing_cost)`.
2. **Tax profile default:** CA MFJ — combined **marginal rate 41%**, **CG exclusion $500,000**, **SALT cap $10,000**, **CG rate 24%** (≈15% federal LTCG + ~9% CA). All editable.
3. **Buyer housing cost** = PITI + maintenance − (annual tax shield / 12), where shield uses that year’s mortgage interest + `min(property_tax, SALT)`.
4. **Buy net worth** each year = liquid proceeds after sell costs and loan − CG tax on taxable gain + **buyer investment portfolio**.
5. **Rent net worth** = renter portfolio seeded with `cash_to_close` (unchanged opportunity-cost idea).
6. **Cost basis** for CG = effective purchase price (list/offer); closing costs not added to basis in v1.
7. If housing cost > budget → that path invests $0 (no borrowing).
8. Simplified model — not a full Form 1040/540; UI captions say so.

## Formula

### Tax shield (year `y`, months `12y+1 .. 12(y+1)` or schedule slice)

```text
interest_y = sum of interest in amortization months for year y→y+1
             (for advancing year y’s cash flows after the year-y snapshot)
prop_deduct = min(annual_property_tax, salt_cap)
shield_y = marginal_rate/100 * (interest_y + prop_deduct)
owner_after_tax_monthly_y = PITI + maint - shield_y/12
```

Interest for the **first** year of contributions (between Y0 and Y1 snapshots) uses months 1–12; between Y1 and Y2 uses months 13–24; etc.

### Surplus

```text
buy_contrib_y  = max(0, budget - owner_after_tax_monthly_y)
rent_contrib_y = max(0, budget - rent_y)
rent_y = rent0 * (1 + rent_growth)^y   # same growth timing as today for year y+1 advances
```

### Portfolios

Both portfolios compound monthly at `invest_return_pct`:

```text
# Rent starts at cash_to_close; Buy invest portfolio starts at 0
for each month in year:
  portfolio *= (1 + r_month)
  portfolio += contrib
```

### Buy liquidation (snapshot at year `y`)

```text
home = price0 * (1+appr)^y
amount_realized = home * (1 - sell%)
loan = balance at month 12*y (year 0: loan0)
gain = amount_realized - basis   # basis = effective_price
taxable = max(0, gain - cg_exclusion)
cg_tax = taxable * (cg_rate/100)
buy_nw = amount_realized - loan - cg_tax + buy_portfolio
rent_nw = rent_portfolio
```

## Persistence

New `FinancialAssumptions` columns (defaults as above):

| Column | Default |
|--------|---------|
| `monthly_budget` | 13000 |
| `marginal_tax_pct` | 41 |
| `cg_tax_pct` | 24 |
| `cg_exclusion` | 500000 |
| `salt_cap` | 10000 |

## UI

Buy vs rent section: Budget, marginal tax %, CG rate %, CG exclusion $, SALT cap $ — with short MFJ captions. Chart caption mentions after-tax owner cost + two-way surplus + CG on sale.

## Tests

- Two-way: when rent == after-tax owner == budget, both portfolios only grow from seed (buy seed 0).
- When budget > both costs, both accumulate contributions.
- Tax shield reduces owner cost → smaller buy surplus than pre-tax.
- CG: gain below exclusion → cg_tax 0; above → tax applied.
- Leverage still: equity grows faster than home price early years.
- Backward-compatible defaults when new kwargs omitted.

## Out of scope

NIIT split, CA Form 540 fidelity, standard-vs-itemize switch, points, basis += closing, renters’ insurance.
