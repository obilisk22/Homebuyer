# Rent growth + rent control on Buy vs rent — Design Spec

**Date:** 2026-07-18  
**Status:** Approved for implementation  
**Product:** Homebuy Financials — Buy vs rent chart  
**Approach:** Persist rent-control toggle + growth %; ACS county median-rent ~5y CAGR when control is off

## Goal

Rent in the buy-vs-rent projection should rise over time instead of staying flat. A **Rent control** checkbox next to Comparable rent forces **2%/yr**. When unchecked, growth comes from **Census ACS county median gross rent CAGR** over ~5 years. Owner PITI stays flat (v1).

## Locked decisions

| Decision | Choice |
|----------|--------|
| UI | Checkbox next to rent section |
| Rent control on | Fixed **2%/yr** growth |
| Rent control off | ACS county **B25064** CAGR (~latest ACS year vs 5 years earlier) |
| Geography | County via FCC FIPS from pin (not city proper) |
| Owner costs | PITI flat for entire horizon |
| ACS failure / no key | Default growth **3%**, source `Default` |
| Persistence | `rent_control`, `rent_growth_pct`, `rent_growth_source` on `FinancialAssumptions` |
| Out of scope v1 | Ownership inflation; city-level ACS; editable 6%/10% invest/sell |

## Behavior

### UI

- **Rent control** checkbox beside Comparable rent / month.
- Quiet caption under rent: e.g. `Growth 2.00%/yr · Rent control 2%` or `Growth 3.41%/yr · ACS county ~5y CAGR`.
- Chart caption also mentions rent growth % + source.
- Save / Recalculate / Enter include the new fields.

### Projection math

Extend `buy_vs_rent_projection(..., rent_growth_pct: float = 0.0)`:

- Buy path unchanged.
- For each year \(t\), monthly rent used that year:  
  `rent(t) = monthly_rent₀ × (1 + rent_growth_pct/100)^t`
- Each month in year \(t\):  
  `contrib = max(0, PITI − rent(t))`  
  then compound at 10%/12 as today.
- Year 0 uses `rent₀` (no growth yet).

### Toggle / sync rules

| Action | Result |
|--------|--------|
| Check rent control | `rent_control=True`, `rent_growth_pct=2`, `rent_growth_source="Rent control 2%"` |
| Uncheck rent control | `rent_control=False`; re-resolve ACS (or Default); clear Manual |
| ACS success (control off, not Manual) | Set `rent_growth_pct` to CAGR %; source `ACS county ~5y CAGR` |
| ACS fail | `rent_growth_pct=3`, source `Default` |
| User edits growth % | `rent_growth_source="Manual"`; uncheck rent control |
| Listing add / Refresh | Re-resolve growth unless source is `Manual` **and** rent control is off; if rent control on, keep forcing 2% |

Loan terms never overwritten. Monthly rent autofill rules unchanged.

## Data — ACS rent CAGR

New helper (prefer `app/core/census_acs.py` or thin `app/core/rent_growth.py`):

1. `county_fips_for(lat, lng)` (existing).
2. Fetch ACS 5-year median gross rent `B25064_001E` for the county for `ACS_YEAR` and `ACS_YEAR - 5` (same year constant as map overlays).
3. If both rents > 0:  
   `cagr_pct = ((rent_end / rent_start) ** (1/5) − 1) * 100`
4. Cache JSON under `data/cache/` (reuse overlay cache helpers).
5. Requires `CENSUS_API_KEY`; return `None` on miss.

Call from `_sync_financial_from_listing` / a dedicated `ensure_rent_growth(prop)` used on refresh and when unchecking rent control.

## Persistence

| Column | Type | Default |
|--------|------|---------|
| `rent_control` | bool | `false` |
| `rent_growth_pct` | float | `3.0` |
| `rent_growth_source` | str | `""` |

SQLite `ALTER` via `_migrate_sqlite`.

## Architecture

```
UI checkbox / Save / Recalculate
  → FinancialAssumptions (rent_control, rent_growth_pct, source)
  → buy_vs_rent_projection(..., rent_growth_pct)

Listing refresh / uncheck control
  → ACS county B25064 CAGR (or 2% if control)
  → write growth fields
```

Touched areas: `finance.py`, `census_acs.py` (or `rent_growth.py`), `models.py`, `db.py`, `property_service.py`, `financial.py`, tests, `AGENTS.md`, `README.md`.

## Edge cases

| Case | Behavior |
|------|----------|
| No lat/lng or Census key | 3% / `Default` + muted warning |
| Zero or missing ACS rents | Same |
| Negative ACS CAGR | Allowed; show in caption |
| Rent = 0 | Growth math still applies (stays 0); keep “set rent” hint |
| Network fail | Keep last good growth fields |
| Rent control on | Always 2%; skip ACS until unchecked |

## Testing

- Unit: rent CAGR from two rents / five years.
- Unit: `buy_vs_rent_projection` with growth — year-1 contribution uses `rent₀×(1+g)`.
- ACS helper: fixture responses; no live Census in CI.
- Sync: control on → 2%; off → ACS mock; Manual preserved until control toggled.

## Docs (on implementation)

Update `AGENTS.md` decision 6d / Financials section and `README.md`: rent control checkbox, ACS county CAGR, PITI flat, default 3%.

## Non-goals (v1)

- Inflating tax / insurance / HOA
- City or tract ACS rent series
- State rent-control law detection (checkbox is an assumption, not a legal lookup)
- Changing Gemini fingerprint
