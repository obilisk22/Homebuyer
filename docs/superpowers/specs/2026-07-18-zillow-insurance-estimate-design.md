# Prefer Zillow homeowners insurance estimate — Design Spec

**Date:** 2026-07-18  
**Status:** Implemented  
**Product:** Homebuy Financials autofill  

## Goal

Match the **Home Insurance** estimate shown on the Zillow listing page when we can scrape it. Keep the state average-premium table only as a last resort.

## Locked decisions

| Decision | Choice |
|----------|--------|
| Priority | Zillow estimate → state avg table → $0 |
| Zillow value | Same modeled estimate Zillow shows (not a carrier quote) |
| Fallback | Existing `home_insurance_rates.json` scaled by list price |
| Scope | Improve scrape/extract only; no county/city premium tables |

## Behavior

1. Extract annual homeowners insurance from listing HTML/JSON more aggressively than today (`annualHomeownersInsurance` on property + `resoFacts`, alternate key names, regex / deep walk of `__NEXT_DATA__` / `gdpClientCache`).
2. If found → `annual_insurance` + source `Zillow` (unchanged caption).
3. If missing → existing `resolve_annual_insurance` state-table path (`Estimated: {ST} avg premium`).
4. On add / Refresh listing details, sync overwrites insurance when resolved (same as today).

## Non-goals

- Real insurer quotes  
- County/city premium tables  
- Changing tax / HOA / loan autofill  

## Testing / docs

- Listing extract fixtures for insurance under nested / alternate keys  
- Existing resolve tests remain  
- Update AGENTS.md / README.md if scrape notes change  
