# Buy vs rent + invest chart — Design Spec

**Date:** 2026-07-18  
**Status:** Approved for implementation  
**Product:** Homebuy Financials tab  
**Approach:** Projection math + new Plotly dual-line chart (v1)

## Goal

Add a Financials chart that compares **buy net worth over time** (home appreciates; sell each year for the plot) against **rent + invest the rest** at 10% annual compounding. Appreciation is a real metro/ZIP-informed rate: average of FHFA ZIP decade CAGR and Zillow listing decade appreciation when both exist.

## Locked decisions

| Decision | Choice |
|----------|--------|
| Chart type | Net worth over years 0 … loan term |
| Buy NW at year \(t\) | `home_value(t) − loan_balance(t) − 6% × home_value(t)` (assume sell) |
| Rent path | Invest cash-to-close + monthly `(PITI − rent)` at 10%/yr compounded monthly |
| When rent > PITI | Monthly contribution = 0 (no forced portfolio borrow) |
| Appreciation | Mean of available `{FHFA ZIP ~10y CAGR, Zillow decade %}`; default 3% if both missing |
| Rent source | Zillow `rentZestimate` prefill + manual override |
| Invest return / sell cost | Fixed 10% and 6% in v1 (captioned, not editable) |
| Horizon | Loan term years; yearly plotted points |
| Out of scope v1 | Rent inflation, tax growth, maintenance, deductions, editable 6%/10%, Gemini fingerprint changes |

## Behavior

### Buy line

1. Start `home_value₀` = effective price (offer if set, else list).
2. Each year: `home_valueₜ = home_value₀ × (1 + appreciation_pct/100)^t`.
3. `loan_balanceₜ` from existing amortization schedule (end of year \(t\), month \(12t\); year 0 = full loan).
4. Buy NWₜ = `home_valueₜ − loan_balanceₜ − 0.06 × home_valueₜ`.

### Rent + invest line

1. Year 0 start: portfolio = cash-to-close (down + closing). Same dollars not spent on buying.
2. Each month: housing budget = constant owner `monthly_total` from `summarize()` (P&I + tax + insurance + HOA + PMI). PMI matches the existing calculator (flat from initial down %, not a declining-LTV schedule).  
   Contribution = `max(0, monthly_total − monthly_rent)`.
3. Portfolio compounds at `0.10/12` per month after each contribution.
4. Plot year-end portfolio values.

### Caption (always)

Show FHFA CAGR, Zillow decade %, blended %, rent source, and fixed assumptions (6% sell / 10% invest). Warn when rent is 0 or appreciation fell back to default.

### Recalculate

Chart redraws with Enter / Recalculate from current deal + rent + appreciation fields. Zillow/FHFA lookups run on add / Refresh listing details (and FHFA cache miss), not every keystroke.

## Data sources

### Zillow listing extract

Extend `app/core/zillow_listing.py` to pull:

- `rent_zestimate` — monthly rent estimate when present in listing HTML/JSON
- `appreciation_decade_pct` — numeric ~10-year area appreciation % when Zillow exposes it (probe live listing blobs; prefer structured JSON over brittle UI copy)

Synced on add / **Refresh listing details** via the existing listing sync path (alongside tax/insurance autofill).

### FHFA HPI

New `app/core/fhfa_hpi.py`:

- Download FHFA five-digit ZIP annual all-transactions developmental index (public XLSX/CSV; **no API key**)
- Cache under `data/cache/` with ~30-day TTL; one shared file for all properties
- For `Property.zip_code`, compute ~10-year CAGR from index levels:  
  `(index_end / index_start) ^ (1/n) − 1`
- If ZIP absent from file: try 3-digit ZIP series if available; else mark FHFA unavailable (do not invent a metro match without a clear ZIP→CBSA map in v1)

### Blend

```
available = [r for r in (fhfa_cagr, zillow_cagr) if r is not None]
blended = mean(available) if available else 3.0  # Default
```

Store components for captions even when user overrides the blended field.

## Persistence

Add columns on `FinancialAssumptions` (SQLite `ALTER` via `_migrate_sqlite`):

| Column | Type | Purpose |
|--------|------|---------|
| `monthly_rent` | float | Rent used in projection |
| `rent_source` | str | e.g. `Zillow`, `Manual`, `""` |
| `appreciation_pct` | float | Blended (or overridden) annual % |
| `appreciation_source` | str | e.g. `FHFA+Zillow`, `FHFA`, `Zillow`, `Default`, `Manual` |
| `appreciation_fhfa_pct` | float nullable | Last looked-up FHFA CAGR |
| `appreciation_zillow_pct` | float nullable | Last scraped Zillow decade % |

**Autofill rules** (mirror tax/insurance spirit):

- On listing refresh: set `monthly_rent` from rentZestimate when `rent_source` is empty or `Zillow`; set Zillow appreciation component always when found; recompute blended into `appreciation_pct` when `appreciation_source` is not `Manual`.
- User edit of rent → `rent_source = Manual`.
- User edit of appreciation % → `appreciation_source = Manual` (keep FHFA/Zillow component columns for caption).

Loan terms remain never overwritten by this feature.

## Architecture

```
Listing refresh / add
  → zillow_listing extract (rent + decade %)
  → fhfa_hpi.zip_cagr(zip)
  → PropertyService sync onto FinancialAssumptions

Financials Recalculate
  → summarize(...)  # existing PITI + schedule
  → buy_vs_rent_projection(...)  # new in finance.py
  → Plotly dual-line chart in financial.py module
```

### New / touched modules

| Area | Path |
|------|------|
| Projection math | `app/core/finance.py` — `buy_vs_rent_projection` |
| FHFA lookup | `app/core/fhfa_hpi.py` |
| Listing fields | `app/core/zillow_listing.py` |
| Sync + migrate | `app/core/property_service.py`, `app/core/models.py`, `app/core/db.py` |
| UI chart + fields | `app/modules/financial.py` |
| Tests | `tests/test_core.py` (or dedicated), listing fixtures, FHFA fixture |

Keep modules thin; shared logic in `app/core/`. Chart styling reuses `_CHART` / `_chart_layout` (cyan buy, magenta rent+invest).

## UI placement

1. Existing hero metrics + Your deal / Loan / Ownership unchanged.
2. Small **Buy vs rent** inputs: Monthly rent ($) + Appreciation (%/yr) with source captions under each (same pattern as tax/insurance captions).
3. Existing three charts, then **new** dual-line chart titled e.g. “Buy vs rent + invest (net worth)”.
4. Caption under chart; empty/warning states use existing Financials empty-state patterns when price missing.

## Edge cases

| Case | Behavior |
|------|----------|
| No ZIP / FHFA miss | Zillow-only blend; caption notes FHFA unavailable |
| No Zillow decade % | FHFA-only; caption notes |
| Both missing | `appreciation_pct = 3`, source `Default`, muted warning |
| No rentZestimate | `monthly_rent = 0` until user types; chart draws; caption warns |
| No price / empty schedule | Hide or skip chart with quiet empty hint |
| FHFA / Zillow fetch fail | Keep last good DB/cache values; never crash Financials tab |
| PMI | Included via constant `summarize().monthly_total` (same flat PMI as the rest of Financials) |

Year 0 buy NW is often negative or small (down payment minus 6% of price) — that is intentional honesty for an immediate sale.

## Testing

- Unit: FHFA CAGR from tiny in-memory/fixture index series; blend/fallback/default 3%.
- Unit: `buy_vs_rent_projection` golden cases (fixed price, down, rent, rates → known year-N values).
- Listing extract fixtures for rentZestimate + appreciation when sample HTML/JSON is captured.
- No live FHFA or Zillow network in CI; cache/download mocked or fixture-backed.

## Docs (on implementation)

Update `AGENTS.md` and `README.md`: Financials buy-vs-rent chart, FHFA cache, rentZestimate/appreciation fields, product decision row.

## Non-goals (v1)

- Editable invest return or selling-cost %
- Rent / tax / insurance inflation schedules
- Maintenance, HOA special assessments, tax deductions
- Changing Gemini financial fingerprint or commentary to include this chart
- Map overlay for HPI
- Redfin or other sale-price series as a third appreciation input
