# Homebuy — Product backlog

Filed 2026-07-17. **Refer by number:** say “do TODO-001”, etc.

| # | Status | One-liner |
|---|--------|-----------|
| TODO-001 | Done | Richer Zillow scrape (beds, price, sqft, HOA, year built, home type) |
| TODO-002 | Partial | Area signals — flood/income/crime done; AQI, fire, avg price open |
| TODO-003 | Done | Cost/Sqft display *(list price ÷ sqft)* |
| TODO-004 | Done | Neighborhood: Gemini cool things to do |
| TODO-005 | Done | Financials: Gemini breakdown + opinion |
| TODO-006 | Done | Clean up codebase |
| TODO-007 | Done | Remove per-photo Remove button |
| TODO-008 | Done | Larger / denser gallery |
| TODO-009 | Pending | Honest Gemini neighborhood prompt |
| TODO-010 | Done | Map + Street View combined |

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

**Add:** crime, median income, air quality, fire risk, average home price.

**Status (2026-07-18):** Partial — Map tab layer toggles for **FEMA flood**, **ACS median income**, and **LA County (LAPD Socrata + Santa Monica CKAN) + Seattle crime**. UX = toggles only (no Neighborhood chips). Still pending: air quality, fire risk, average home price / Redfin / ACS home-value choropleth.

**Notes**
- See [`docs/RESEARCH.md`](RESEARCH.md). Core helpers: `census_acs.py`, `fema_flood.py`, `crime_socrata.py`, `crime_density.py`, `overlay_cache.py`.
- Income requires `CENSUS_API_KEY` (documented in `.env.example`).
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

**Status:** Done (2026-07-18)

**In the Financials tab:** ask Gemini for a financial breakdown and an opinion on the property’s finances (offer, PITI, taxes/insurance assumptions, HOA, etc.).

**Shipped**
- Columns `financial_gemini` + `financial_gemini_for` on `Property` (fingerprint `fin_v1|list|offer|down|rate|term|tax|ins|hoa|closing`).
- Helper `app/core/gemini_financial.py` builds a prompt from `summarize()` calculator outputs + assumptions; asks for markdown Breakdown + Opinion sections.
- `PropertyService.ensure_gemini_financial` caches by fingerprint; UI section below charts with Ask / Regenerate; stale take when assumptions change.

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

**Deferred (later pass):** unify `_format_price` / `_money` helpers; merge address parsers; overview cache key bump (TODO-009).

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

## TODO-009 — Honest Gemini neighborhood prompt

**Rewrite the Neighborhood Gemini overview prompt** so it is less flowery/positive and gives a candid, realistic assessment (tradeoffs, noise, cost, drawbacks — not a sales pitch).

**Notes**
- Update `PROMPT_TEMPLATE` (or equivalent) in `app/core/gemini_neighborhood.py`.
- Bump or invalidate cache (`neighborhood_gemini_for`) so old rosy paragraphs aren’t kept forever after the prompt change.
- Keep the “AI may be wrong — verify” disclaimer.

**Touch:** `app/core/gemini_neighborhood.py`, tests for prompt text, maybe force-regenerate UX copy

---

## TODO-010 — Combine Map + Street View into one tab ✅ Done

**Merge the Street View tab into the Map tab:** show the map on top, with Street View directly below it in the same **Map** panel. Remove the standalone Street View tab.

**Done:** Map tab renders Leaflet + free `svembed` Street View below. `street_view.py` keeps helpers only (no `MODULE` tab). No paid Maps Embed API.

**Touch:** `app/modules/map_view.py`, `app/modules/street_view.py`, `AGENTS.md` / `README.md`