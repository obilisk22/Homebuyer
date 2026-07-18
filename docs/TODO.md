# Homebuy — Product backlog

Filed 2026-07-17. **Refer by number:** say “do TODO-001”, etc.

| # | Status | One-liner |
|---|--------|-----------|
| TODO-001 | Done | Richer Zillow scrape (beds, price, sqft, HOA, year built, home type) |
| TODO-002 | Partial | Area signals — flood/zoning/ACS/crime done; AQI, fire, Redfin open |
| TODO-003 | Done | Cost/Sqft display *(list price ÷ sqft)* |
| TODO-004 | Done | Neighborhood: Gemini cool things to do |
| TODO-005 | Done | Financials: Gemini breakdown + opinion |
| TODO-006 | Done | Clean up codebase |
| TODO-007 | Done | Remove per-photo Remove button |
| TODO-008 | Done | Larger / denser gallery |
| TODO-009 | Done | Honest Gemini neighborhood prompt |
| TODO-010 | Done | Map + Street View combined |
| TODO-011 | Done | Financials: autofill list/HOA/tax/insurance from Zillow + ACS/state tables |
| TODO-012 | Done | Financials: autofill interest rate from Freddie Mac PMMS by loan term |

---

## TODO-001 — Richer Zillow listing scrape

**Status:** Done (2026-07-18)

**Scrape / parse from the Zillow listing:** beds, price, square footage, HOA cost, year built, home type.

**Shipped**
- Columns on `Property`: `sqft`, `hoa_fee` (monthly $), `year_built`, `home_type`.
- Extraction prefers unescaped `gdpClientCache` walk, then LD+JSON / meta / regex fallbacks (`app/core/zillow_listing.py`).
- Shown on library cards, property header meta line, and Edit listing details; wired into add-from-Zillow + **Refresh listing details**.

**Touch:** `app/core/zillow_listing.py`, `models.py`, `property_service.py`, `app/ui/pages.py`, tests

---

## TODO-002 — Area risk & market signals (partial)

**Add:** crime, median income, air quality, fire risk, average home price / demographics.

**Status (2026-07-18):** Partial — Map tab layer toggles for **FEMA flood**, **Zoning** (LA City / Santa Monica / County), **ACS** demographics, and **LA County + Seattle crime** (hex density). Still pending: air quality, fire risk, Redfin sale-price choropleth.

**Notes**
- See [`docs/RESEARCH.md`](RESEARCH.md). Core helpers: `census_acs.py`, `fema_flood.py`, `crime_socrata.py`, `crime_density.py`, `overlay_cache.py`.
- ACS layers require `CENSUS_API_KEY` (documented in `.env.example`).
- Crime: LA County (LAPD Socrata + Santa Monica CKAN) + Seattle; Map shows a **hex density choropleth** (not dots); other cities get a clear “no crime layer” state.

**Touch:** `app/modules/map_view.py`, `app/core/*` overlay clients

---

## TODO-003 — Display cost per square foot ✅ Done

**Show Cost/Sqft** (list price ÷ living area).

**Done:** Library cards + property header meta line show `$N/sqft` when both `list_price` and `sqft` are set (`_format_price_per_sqft` in `pages.py`).

**Touch:** `app/ui/pages.py`

---

## TODO-004 — Neighborhood: “Cool things to do” (Gemini)

**Status:** Done (2026-07-18)

**Add a Neighborhood-tab section** that asks Gemini for cool things to do nearby (given neighborhood + city).

**Shipped**
- Columns `neighborhood_things_to_do` + `neighborhood_things_to_do_for` (cache key `things_v2|name|city|state`).
- Prompt prioritizes walking-distance places and requires a Google Maps search markdown link per item.
- Separate prompt/API helper from the vibe overview so regenerating one does not wipe the other.
- UI section under overview: **Ask Gemini: things to do** + Regenerate; cleared when neighborhood override changes.

**Touch:** `app/core/gemini_neighborhood.py`, `models.py`, `db.py`, `property_service.py`, `neighborhood_reviews.py`, tests

---

## TODO-005 — Financials: Gemini breakdown + opinion

**Status:** Done (2026-07-18; revised fin_v4 URL-context)

**In the Financials tab:** ask Gemini for a market / buy-vs-rent opinion grounded in Zillow listing pages.

**Shipped**
- Columns `financial_gemini` + `financial_gemini_for` on `Property` (fingerprint `fin_v4|<url-hash>` over subject + peer Zillow URLs).
- Helper `app/core/gemini_financial.py` prompts with Zillow URLs only; Gemini **URL context** (+ Google Search) fetches listings — no app calculator dump.
- `PropertyService.ensure_gemini_financial` caches by URL fingerprint; UI Ask / Regenerate; stale when library Zillow links change.

**Touch:** `app/modules/financial.py`, `app/core/gemini_financial.py`, `models.py`, `db.py`, `property_service.py`, tests

---

## TODO-006 — Clean up codebase ✅ Done

**Status:** Done (2026-07-18)

**General cleanup pass:** dead code, unused temp/debug leftovers, inconsistent naming, thin modules vs fat core, duplicate helpers, stale comments/docs.

**Shipped (features unchanged)**
- Removed dead helpers/imports (`reset_modules_cache`, Reddit embed URL helpers, `photo_absolute_path`, unused `Path` in `main.py`).
- Single Zillow HTML fetch on add-home (listing details + photos share one page fetch).
- Batched photo import commits; fewer redundant SQLite loads on library/property first paint and module initial render.
- Overlay cache prunes expired files on miss; lazy Plotly import in Financials chart redraw.
- Docs/backlog status sync (crime coverage wording, TODO-006 Done, BUG-002 archived).

**Deferred (later pass):** unify `_format_price` / `_money` helpers; merge address parsers.

**Touch:** repo-wide — `app/core/`, modules, tests, docs

---

## TODO-007 — Remove photo “Remove” button ✅ Done

**Gallery UX:** drop the per-photo **Remove** control.

**Done:** Per-thumb Remove button removed from Photos gallery. Bulk reset remains via **Re-import (replace)**; `PropertyService.delete_photo` kept for re-import cleanup.

**Touch:** `app/modules/gallery.py`

---

## TODO-008 — Larger gallery photos, less negative space ✅ Done

**Gallery layout:** bigger thumbnails / tiles; tighten gaps, padding, and empty chrome so the grid feels denser.

**Done:** Full-width **4-column** gallery grid (`.hb-photo-gallery`); tiles fill the row flush to the right edge; 4:3 thumbs; tighter caption padding. Lightbox unchanged. Per-photo Remove removed (TODO-007).

**Touch:** `app/modules/gallery.py`, `app/ui/theme.py`

---

## TODO-009 — Honest Gemini neighborhood prompt ✅ Done

**Rewrite the Neighborhood Gemini overview prompt** so it is less flowery/positive and gives a candid, realistic assessment (tradeoffs, noise, cost, drawbacks — not a sales pitch).

**Done:** Prompt reframed for long-term homebuying (daily life, noise/traffic/parking, safety nuance, costs, climate risks, who it suits); cache key `overview_v2|…`. UI label: “Gemini neighborhood assessment”.

**Touch:** `app/core/gemini_neighborhood.py`, `property_service.py`, `neighborhood_reviews.py`, tests

---

## TODO-010 — Combine Map + Street View into one tab ✅ Done

**Merge the Street View tab into the Map tab:** show the map on top, with Street View directly below it in the same **Map** panel. Remove the standalone Street View tab.

**Done:** Map tab renders Leaflet + free `svembed` Street View below. `street_view.py` keeps helpers only (no `MODULE` tab). No paid Maps Embed API.

**Touch:** `app/modules/map_view.py`, `app/modules/street_view.py`, `AGENTS.md` / `README.md`

---

## TODO-011 — Financials: autofill from Zillow + ACS/state tables ✅ Done

**Status:** Done (2026-07-18)

**Auto-populate Financials on add/refresh** instead of leaving list price/HOA/tax/insurance at placeholder defaults.

**Shipped**
- Zillow scrape gains `annual_tax`, `tax_assessed_value`, `property_tax_rate`, `annual_insurance` (`app/core/zillow_listing.py`).
- `resolve_annual_property_tax` chain: Zillow annual tax → Zillow assessed × rate → ACS county effective rate (`B25103`/`B25077`) × assessed → × list price (`app/core/property_tax.py`, `census_acs.county_effective_property_tax_rate`).
- `resolve_annual_insurance`: Zillow annual insurance → state avg-premium table scaled to list price (`app/core/home_insurance.py`, `app/data/home_insurance_rates.json`).
- `PropertyService._sync_financial_from_listing` overwrites `list_price`/`monthly_hoa`/`annual_property_tax`/`annual_insurance` from the listing on add, refresh, and post-geocode re-sync; down payment / term / closing are never touched (interest rate: see TODO-012); unresolved tax/insurance fall back to `0` instead of fake defaults; explicit `$0` HOA overwrites but a missing HOA value keeps the previous one.
- New `FinancialAssumptions` columns `property_tax_source` / `insurance_source` (e.g. `Zillow`, `Zillow assessed × rate`, `Estimated: ACS county`, `Estimated: CA avg premium`) surfaced as captions under the Ownership costs inputs.

**Touch:** `app/core/zillow_listing.py`, `app/core/property_tax.py`, `app/core/home_insurance.py`, `app/core/census_acs.py`, `app/core/property_service.py`, `app/core/models.py`, `app/core/db.py`, `app/modules/financial.py`, `.env.example`, tests

---

## TODO-012 — Financials: average mortgage rate by loan term ✅ Done

**Status:** Done (2026-07-18)

**Autofill Interest rate** from national average fixed mortgage rates for the selected loan duration.

**Shipped**
- `app/core/mortgage_rates.py` fetches Freddie Mac PMMS 15-yr / 30-yr averages (HTML primary, FRED data-page fallback), caches under `data/cache/mortgage_rates/` (~6h).
- Term mapping: pick the closer of 15 vs 30 (e.g. 20 → 15-yr, 25 → 30-yr).
- Applied on add/refresh sync + `ensure_financial` unless `interest_rate_source` is `Manual`; changing Term refreshes the matching average; editing the rate marks Manual.
- Caption under Interest rate (e.g. `Freddie Mac PMMS 30-yr FRM · 2026-07-16`).

**Touch:** `app/core/mortgage_rates.py`, `property_service.py`, `models.py`, `db.py`, `app/modules/financial.py`, tests, `AGENTS.md`
