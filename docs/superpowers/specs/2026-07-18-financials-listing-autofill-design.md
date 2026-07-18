# Financials listing autofill — Design Spec

**Date:** 2026-07-18  
**Status:** Approved for planning  
**Product:** Homebuy Financials tab + Zillow listing ingest  

## Problem

The Financials tab is a solid PITI calculator with charts and Gemini commentary, but assumptions start from generic model defaults (`list_price` $500k, tax $6k, insurance $1.8k). The listing scrape already puts `list_price` and `hoa_fee` on `Property`, yet:

1. Scraped **list price is not copied** into `FinancialAssumptions` — Financials can show $500k while the library card shows the real price.
2. **HOA** is only seeded into assumptions when still `0`.
3. Zillow JSON often has **tax / insurance / assessed / rate** fields that are not parsed.
4. When Zillow omits tax, there is no **local (county) effective tax rate** fallback — only a silent fake default.

Goal for this slice: **autofill listing-sourced financial fields from Zillow where possible, then from real local rate data**, and keep loan terms as the user’s.

## Goals

1. On **Add home** and **Refresh listing**, seed/overwrite listing-sourced `FinancialAssumptions` fields from the best available data.
2. Extend the Zillow scrape for tax, insurance, assessed value, and tax rate.
3. Estimate annual property tax with a clear precedence chain ending in **Census ACS county effective rates** (not a national rule of thumb).
4. Estimate insurance from Zillow first, else **price × a published regional/state rate table**.
5. Never overwrite user loan-negotiation fields on refresh.

## Non-goals

- Autofill interest rate, down payment %, loan term, or closing cost % from Zillow ads/estimates.
- Full provenance store on every field (Approach C) — light UI captions only.
- Zestimate / rentZestimate as PITI inputs (optional later Gemini context).
- Changing Gemini fingerprint schema unless new fields require it (current fingerprint already includes tax/ins/hoa/list).
- Map overlay work, codebase-wide cleanup (TODO-006).

## Decisions (locked)

| Decision | Choice |
|----------|--------|
| Approach | **A** — scrape + Census ACS county tax rates + regional insurance table; sync on add/refresh |
| Refresh policy | Overwrite listing-sourced fields on refresh; preserve loan terms |
| Tax basis for rate × value | Prefer **assessed value** when known; else **list price** |
| Tax fallback source | Census ACS county effective rate (median taxes / median value), via existing FCC FIPS + cache patterns |
| Insurance fallback | Data-backed state/regional rate table × price; no fixed $1,800 fill-as-data |
| Unresolved values | After seed attempt: write `0` for unresolved tax/insurance (and missing list price); do not leave $6k/$1.8k/$500k placeholders |
| HOA on refresh | If scrape includes HOA (including explicit 0), overwrite; if omitted entirely, keep previous |
| Offer price | Never touched by sync |
| UI captions | Light one-line source under tax/insurance when useful (e.g. “From Zillow” / “Estimated: {County} ACS”) |

### Fields written by sync (listing-sourced)

| `FinancialAssumptions` field | Source chain |
|------------------------------|--------------|
| `list_price` | Scraped listing price |
| `monthly_hoa` | Scraped monthly HOA (when present on listing payload) |
| `annual_property_tax` | See tax chain below |
| `annual_insurance` | See insurance chain below |

### Fields never written by sync

`offer_price`, `down_payment_pct`, `interest_rate_pct`, `loan_term_years`, `closing_cost_pct`

### Annual property tax resolution

1. Zillow **explicit annual tax** (e.g. latest `taxHistory` amount, `taxAnnualAmount`, resoFacts annual tax).
2. Zillow **assessed value × Zillow `propertyTaxRate`** when both present.
3. **Census ACS county effective rate** × **assessed value if known, else list price**.
4. Unresolved — do not fill with $6,000 as if known.

Requires geocode / FCC FIPS for step 3. Without coords or without a usable Census key/response, skip to unresolved.

### Annual insurance resolution

1. Zillow `annualHomeownersInsurance` (or equivalent scraped field).
2. **List (or effective list) price × regional/state rate** from an in-repo table sourced from a published dataset (document the source in code/comments).
3. Unresolved — do not fill with $1,800 as if known.

### Overwrite rule

- **List price / tax / insurance:** On add/refresh, if the resolver returns a **positive** value, write it. If the listing path ran but that field is **unresolved**, write `0.0` (UI treats 0 as “needs input”) — do **not** leave the old placeholder defaults ($500k / $6k / $1.8k) after a seed attempt when scrape had no better number.
- **Exception — partial omission:** If refresh scrape **omits** a field entirely (e.g. no HOA key in payload) and we cannot distinguish “unknown” from “zero”, keep the previous assumption value rather than wiping it.
- **HOA:** If scrape includes HOA (including explicit `0`), overwrite; if omitted entirely, keep previous.
- Never invent a national average to avoid `0`.

## Architecture

```
Add / Refresh listing
  → fetch_listing_details / extract_listing_details
  → ListingDetails (+ tax/insurance/assessed/rate)
  → PropertyService._apply_listing_details
       → property fields (price, hoa, …)
       → resolve_annual_property_tax(details, lat/lng, price)
       → resolve_annual_insurance(details, price, state)
       → write FinancialAssumptions listing-sourced fields
  → Financials UI reads ensure_financial() (seeded values)
```

## Components

| Piece | Path | Responsibility |
|-------|------|----------------|
| Scrape extension | `app/core/zillow_listing.py` | Parse tax/insurance/assessed/rate into `ListingDetails` |
| Tax resolver | `app/core/property_tax.py` (new) | Precedence chain; call ACS rate helper |
| ACS effective rate | `app/core/census_acs.py` (extend) | County median tax / median home value; cache under `data/cache/` |
| Insurance resolver | `app/core/home_insurance.py` (new) + rate table asset | Zillow → table × price |
| Sync | `app/core/property_service.py` | Apply listing-sourced assumptions on add/refresh |
| Model defaults | `app/core/models.py` | Prefer `0.0` defaults for `list_price`, `annual_property_tax`, `annual_insurance` (and keep `purchase_price` in sync with list when written) so brand-new rows before seed don’t look “researched” |
| UI | `app/modules/financial.py` | Show seeded numbers; optional light source captions |
| Tests | `tests/` | Precedence, overwrite rules, scrape fixtures |

## Error handling

| Case | Behavior |
|------|----------|
| Geocode / FIPS fail | Skip ACS tax step; Zillow-only chain |
| No / invalid Census key or ACS error | Skip ACS; leave tax unresolved if Zillow lacked tax |
| Insurance state missing from table | Leave insurance unresolved |
| Partial listing refresh | Overwrite only fields with successful positive (or explicit HOA 0) results |
| Existing DB rows | Re-seed on next Refresh listing; no mandatory migration |

## Testing

1. Tax precedence: explicit > assessed×rate > ACS×assessed > ACS×list > unset.
2. Insurance: Zillow > table > unset.
3. `_apply_listing_details` / refresh: overwrites list price, HOA, tax, insurance; preserves offer, down, rate, term, closing.
4. Fixture snippets from sample Zillow dumps for tax/insurance keys when available.
5. Existing finance / Gemini fingerprint tests still pass.

## Later roadmap (out of this spec)

Not required to ship autofill; candidate follow-ups for the Financials owner:

- Stronger cash-to-close / PMI transparency; editable PMI rate.
- Zestimate / rent vs ownership helpers (display / Gemini context only).
- Side-by-side offer scenarios.
- Honest “assumptions freshness” after listing price changes.

## Open product notes

- Changing SQLAlchemy defaults to `0.0` for listing-sourced money fields may affect `app/seed.py` / demos — update seed to set explicit values.
- Document the insurance table’s public source next to the asset so rates can be refreshed later without inventing a constant.
- Light UI captions are optional polish once sync works; not a blocker for planning.
