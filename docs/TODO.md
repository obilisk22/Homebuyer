# Homebuy — Product backlog

Filed 2026-07-17. **Refer by number:** say “do TODO-001”, etc.

| # | Status | One-liner |
|---|--------|-----------|
| TODO-001 | Done | Richer Zillow scrape (beds, price, sqft, HOA, year built, home type) |
| TODO-002 | Won't fix | Area signals umbrella — shipped flood/zoning/ACS/crime; no further under this ID |
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
| TODO-013 | Done | Schools: nearby / assigned schools from NCES (map + property panel) |
| TODO-015 | Won't fix | Library pipeline status (Watching / Toured / Offer / Passed / …) |
| TODO-016 | Done | Library financial snapshot columns (PITI, cash-to-close) + CSV/JSON export |
| TODO-017 | Done | Buy-vs-rent: editable invest return, sell cost %, optional maintenance |
| TODO-018 | Done | Side-by-side Compare view (2–4 homes) |
| TODO-020 | Done | Area signals: wildfire + AQI map layers (TODO-002 slice) |
| TODO-021 | Done | Area signals: Redfin ZIP median sale choropleth (TODO-002 slice) |
| TODO-022 | Won't fix | Closing checklist + simple deal timeline module |
| TODO-023 | Won't fix | Document attachments per property (offers, inspection, disclosures) |
| TODO-024 | Done | Zoning overlay: coverage (1102/bbox/pagination) + WS-safe slim/merge (~16 MB → &lt;1 MB) |
| TODO-025 | Done | Library nearby proximity icons (OSM Overpass + optional Google Places) |
| TODO-026 | Done | NiceGUI Connection lost — `run.io_bound` + `app/core/ui_jobs.py` |
| TODO-027 | Open | Remove Home Compare feature (library checkboxes + `/compare`) |
| TODO-028 | Open | Financials UX: collapse rarely-touched fields, per-field revert, hierarchy |
| TODO-029 | Open | Property header: show library nearby-signal icons (bottom-right, above tabs) |
| TODO-030 | Open | Gemini neighborhood prompts: pass exact home address (not only hood name) |
| TODO-031 | Open | Property page: lower visual weight of Edit listing details |
| TODO-032 | Open | Library card: show calculated appreciation %; amber if under 3% |

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

## TODO-002 — Area risk & market signals ❌ Won't fix

**Originally:** crime, median income, air quality, fire risk, average home price / demographics.

**Status:** Won't fix (2026-07-18) — umbrella closed. **Shipped and kept:** FEMA flood, Zoning (LA City / SM / County), ACS demographics, LA County + Seattle crime hex density.

Remaining area-signal ideas from the umbrella are shipped as **TODO-020** (wildfire + AQI) and **TODO-021** (Redfin sale choropleth).

**Touch (shipped):** `app/modules/map_view.py`, `app/core/*` overlay clients

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

---

## TODO-013 — Schools support (NCES)

**Status:** Done (2026-07-18)

**Show school context for a pinned home** so buyers can judge elementary / middle / high options without leaving Homebuy.

**Shipped**
- Free **NCES EDGE** public school points via ArcGIS REST bbox query (`app/core/schools_nces.py`) — no GreatSchools; no national shapefile download.
- **Map:** Schools toggle → markers within ~4 mi + legend; **Nearby schools** panel with distance + NCES deep link.
- Cache under `data/cache/schools_nces/` (~7d).

**Out of scope (v1):** paid ratings APIs, attendance-boundary polygons, walkability.

**Touch:** `app/core/schools_nces.py`, `map_view.py`, tests, `docs/RESEARCH.md` / `AGENTS.md`

---

## TODO-015 — Library pipeline status ❌ Won't fix

**Status:** Won't fix (2026-07-18)

**Was:** shortlist pipeline chips (Watching / Toured / Offer / Under contract / Passed). Not pursuing.

---

## TODO-016 — Library financial snapshots + export

**Status:** Done (2026-07-18)

**Show quick money columns on the library** (e.g. estimated PITI, cash-to-close, $/sqft) derived from saved `FinancialAssumptions`, plus **CSV/JSON export** of library + financials for backup / spreadsheet compare.

**Shipped**
- Quiet `PITI $…/mo · Cash $…` caption on library cards when financials exist (`finance.summarize` via `app/core/library_export.py`).
- Toolbar **Export** → Download CSV / JSON (properties + key financial fields).
- `$/sqft` already on library chips (TODO-003).

**Touch:** `pages.py`, `app/core/library_export.py`, tests

---

## TODO-017 — Buy-vs-rent editable assumptions

**Status:** Done (2026-07-18)

**Make buy-vs-rent what-ifs editable:** invest return %/yr, sell cost %, optional monthly maintenance — instead of fixed 10% / 6% only.

**Shipped**
- Columns `invest_return_pct` (default 10), `selling_cost_pct` (default 6), `monthly_maintenance` (default 0) on `FinancialAssumptions` + SQLite migrate.
- `buy_vs_rent_projection` takes these params (backward-compatible defaults); maintenance adds to PITI for the rent surplus.
- Financials **Buy vs rent** section: number inputs + captions; Save / Recalculate / charts use live values.

**Touch:** `models.py`, `db.py`, `finance.py`, `financial.py`, `tests/test_buy_vs_rent.py`

---

## TODO-018 — Side-by-side Compare view

**Status:** Done (2026-07-18)

**Compare 2–4 shortlisted homes** on one page: price, $/sqft, beds/baths, PITI, cash-to-close (no status column — TODO-015 won't fix).

**Shipped**
- Library checkboxes (max 4) + **Compare** → `/compare?ids=…`.
- Table of address / list / offer / $/sqft / beds·baths / PITI / cash-to-close; back link + open-property buttons.
- Helpers in `app/core/compare.py` (reuses library snapshots).

**Touch:** `pages.py`, `app/core/compare.py`, `app/main.py` route import, tests

---

## TODO-020 — Wildfire + AQI map layers

**Status:** Done (2026-07-18)

**Shipped**
- **Wildfire:** USFS RMRS Wildfire Hazard Potential 2023 WMS (`app/core/wildfire_whp.py`) — no key; legend for WHP classes.
- **AQI:** Open-Meteo US AQI grid → hex choropleth (`app/core/air_quality.py`) — no key; graceful status if the API fails.
- Exclusive Map toggles **Wildfire** / **AQI** alongside existing overlays.

**Touch:** `wildfire_whp.py`, `air_quality.py`, `map_view.py`, tests

---

## TODO-021 — Redfin ZIP median sale choropleth

**Status:** Done (2026-07-18)

**Shipped**
- Streams Redfin Data Center zip market tracker TSV (gzip) once → slim `zip → median_sale_price` cache (`app/core/redfin_sales.py`).
- Joins to TIGER ZCTA polygons near the pin; muted fill + popup note when a ZIP has no Redfin median.
- Map toggle **Sale price**; first enable may take a minute while the national file is ingested.

**Touch:** `redfin_sales.py`, `map_view.py`, cache, tests

---

## TODO-022 — Closing checklist + deal timeline ❌ Won't fix

**Status:** Won't fix (2026-07-18)

**Was:** post-offer closing checklist + timeline module. Not pursuing.

---

## TODO-023 — Document attachments per property ❌ Won't fix

**Status:** Won't fix (2026-07-18)

**Was:** document vault for offers / inspection / disclosures. Not pursuing.

---

## TODO-024 — Zoning overlay coverage gaps

**Status:** Done (2026-07-18)

**Problem:** The Map **Zoning** layer only painted zoning in a few pockets near the pin. Those pockets already looked right (colors, labels, neo styling) — appearance kept. The bug was **coverage**: most of the visible map stayed empty. After layer/bbox/pagination fixes, Zoning could still appear empty: Python returned thousands of parcels and status claimed success, but Leaflet never drew polygons.

**Root cause (verified live against ZIMAS):**
1. **Wrong layer:** City of LA used MapServer **1101** (Zoning Chapter 1A) — rollout-only pockets (e.g. parts of Downtown). Westside / Hollywood / Venice returned **0** features on 1101 while **1102** (citywide Zoning) filled the same bbox continuously.
2. **Tiny bbox:** `DEFAULT_HALF_SPAN_DEG = 0.012` (~0.8 mi half) left most of the Map viewport empty vs ACS-scale overlays (~0.04°).
3. **No pagination:** At a larger bbox, ArcGIS `exceededTransferLimit` truncated to one page → sparse parcels.
4. **SM bbox steal:** Loose Santa Monica bbox + check-before-LA-name routed some Westside LA pins (e.g. Mar Vista) to SCAG `CITY='Santa Monica'` → SM-only pockets.
5. **WebSocket buffer (remaining bug after 1–4):** Mar Vista pin returned **~3494** parcels ≈ **~16.2 MB** GeoJSON. NiceGUI/engineio `max_http_buffer_size` default is **1 MB**, so the Zoning payload was dropped on the wire (ACS income for the same pin is ~0.47 MB and works). Layer 1102 + pagination were correct; the Map toggle looked on / status updated while polygons never arrived.

**Fix:** Query ZIMAS **1102**; raise default half-span to **0.04°**; paginate ArcGIS GeoJSON (`resultOffset` / `PAGE_SIZE`); LA city name beats SM bbox; tighten SM eastern edge; status caption includes `~N mi radius`. WS buffer **32MB**; full parcel geometry; when ArcGIS truncates at **5000**, binary-search largest pin-centered complete span (cache **v6**).

**Verify:** Restart app → City of LA pin → Map → Zoning → continuous proper parcel polygons; status like `Zoning: N parcels (City of Los Angeles (ZIMAS)) · ~2.8 mi radius`.

**Touch:** `app/main.py`, `app/core/zoning_gis.py`, `tests/test_zoning_gis.py`, docs.

---

## TODO-025 — Library nearby proximity icons

**Status:** Done (2026-07-18)

**At-a-glance proximity badges** on library cards: highway, transit, playground, grocery, shelter/recovery — only when within distance thresholds.

**Shipped**
- `app/core/nearby_signals.py` — OSM Overpass for all five; Google Places Nearby Search for grocery + shelter when `GOOGLE_MAPS_API_KEY` set (OSM fallback without key).
- Cached JSON on `Property` (`nearby_signals`, `nearby_signals_at`); raw responses under `data/cache/nearby/` (~7d).
- Compute on add + post-geocode; library load refreshes up to 3 stale/missing pins (> ~30 days).
- Soft neo chips on the library card bottom-right (not over the photo; magenta risks, lime amenities); distance + name tooltips; chip click does not open card.

**Non-goals (v1):** Map markers, property Nearby panel, manual refresh, library filters by signal.

**Touch:** `nearby_signals.py`, `models.py`, `db.py`, `property_service.py`, `pages.py`, `theme.py`, `tests/test_nearby_signals.py`

---

## TODO-026 — NiceGUI “Connection lost” during long work

**Status:** Done (2026-07-18)

**Problem:** Sync blocking I/O (Zillow scrape, geocode, nearby, Gemini, map overlay fetches) ran on the event loop inside button handlers, freezing WebSocket heartbeats → “Connection lost”.

**Fix**
- `app/core/ui_jobs.py` — session-safe workers (`get_session()` inside the thread; plain values in/out; never pass ORM/UI objects).
- Long UI handlers use `await run.io_bound(job, …)`: library add / refresh / Gemini insights / stale nearby; Map heavy overlays + re-geocode; Financials Gemini; Neighborhood Ask / Refresh.
- Flood/wildfire stay sync (instant WMS); `wire_layer` awaits awaitable handlers.

**Touch:** `ui_jobs.py`, `pages.py`, `map_view.py`, `financial.py`, `neighborhood_reviews.py`, docs.

---

## TODO-027 — Remove Home Compare feature

**Status:** Open

**Remove** the side-by-side Compare flow shipped as TODO-018. Keep library financial captions + CSV/JSON export (TODO-016).

**Delete / unwind**
- Library card checkboxes + **Compare** toolbar button + selection state.
- `/compare` page route and helpers (`compare_page`, `_compare_street`).
- `app/core/compare.py` + `tests/test_compare.py`.
- Docs / AGENTS / README mentions of Compare (product decision §8 + verify checklist).

**Keep:** Export menu, PITI/cash card captions, rest of library chrome.

**Touch:** `app/ui/pages.py`, `app/main.py` (route import), `app/core/compare.py`, tests, `AGENTS.md`, `README.md`, this file.

---

## TODO-028 — Financials page cleanup (hierarchy + defaults)

**Status:** Open

**Problem:** The Financials tab lays out nearly every assumption at once (Your deal / Loan / Ownership / Buy vs rent tax knobs). Fields that rarely change compete with offer/down and the charts.

**Goals**
1. **Primary surface** — keep always-visible only what you tweak often: **Your deal** (offer + down $), hero monthly / charts, and the buy-vs-rent inputs you actually dial (comparable rent + rent control at minimum). Tighten visual hierarchy (deal + results dominate; secondary chrome quieter).
2. **Collapse the rest** — put infrequently edited variables behind one (or a few) **dropdown / expansion(s)**, e.g. Loan defaults (list, rate, term, closing), Ownership (tax, insurance, HOA, maintenance), Advanced buy-vs-rent (appreciation, invest return, sell cost, monthly budget, marginal tax, CG tax/exclusion, SALT). Exact grouping decided at implement time; preserve source captions when shown.
3. **Revert to default on every field** — each editable input gets a control that restores that field’s product default / autofill baseline (e.g. PMMS rate, listing tax/insurance, age-blend maintenance, rent $5300/`Default`, invest 10%, sell 6%, budget $13k, tax 41%, CG 24% / $500k, SALT $10k, etc.). Clearing Manual override where source tracking exists. Prefer per-field, not only “reset all.”

**Non-goals:** Change mortgage math; remove Gemini panel; redesign charts.

**Touch:** `app/modules/financial.py`, `app/ui/theme.py` (form hierarchy CSS as needed), possibly small helpers for default resolution, docs / visual rule if hierarchy changes.

---

## TODO-029 — Nearby icons on property header

**Status:** Open

**Show the same library-card nearby proximity icons** (TODO-025: highway / transit / playground / grocery / shelter) on the **property page header**, bottom-right of the hero — **above the module tabs**.

**Goals**
- Reuse cached `Property.nearby_signals` + existing chip helpers (`hits_in_order`, tooltips, magenta risk / lime amenity).
- Position bottom-right of `.hb-property-hero` (or shell edge above tabs); readable on bleed photo + scrim and beside mode.
- Same fixed order / thresholds as library; no new Map markers or filters.

**Non-goals:** Recompute signals on every property open (use cache; optional best-effort refresh is fine if already cheap). Don’t change library card placement.

**Touch:** `app/ui/pages.py` (property header), `app/ui/theme.py` (header icon placement), docs.

---

## TODO-030 — Gemini: exact home address (not only neighborhood)

**Status:** Open

**Problem:** Neighborhood Gemini (overview + things-to-do) prompts only get `{neighborhood}` + city/state (`app/core/gemini_neighborhood.py`). Answers are hood-generic and miss block-level context for the listing.

**Goals**
- Pass the property’s **exact street address** (and keep neighborhood name when known) into overview + things-to-do prompts so Gemini can reason about the specific location (walkshed, adjacent arterials, micro-area).
- Wire address from `Property.address` (and city/state as today) through `generate_neighborhood_overview` / `generate_things_to_do` + `PropertyService.ensure_gemini_*`.
- **Bump cache keys** (`neighborhood_gemini_for` / `things_v*` prefix) so old hood-only caches invalidate; Regenerate still works as today.

**Out of scope:** Financials Gemini already uses Zillow URLs (URL context) — leave unless a small address label helps; do not dump calculator fields into neighborhood prompts.

**Touch:** `app/core/gemini_neighborhood.py`, `property_service.py`, tests, `AGENTS.md` §6.

---

## TODO-031 — Quieter “Edit listing details”

**Status:** Open

**Problem:** On the property page, **Edit listing details** sits as a full-width expansion under the header actions and competes with Photos / Map / Neighborhood / Financials.

**Goals**
- Lower its visual weight: quieter/greyed expansion chrome, and/or relocate (e.g. under a ⋮ overflow, footer of header, or collapsed “Advanced” near Refresh listing details).
- Keep all existing edit fields + Save behavior; no new listing fields.
- Match dark neo / Creato hierarchy — secondary control, not a peer of the tab strip.

**Touch:** `app/ui/pages.py`, `app/ui/theme.py` as needed, docs.

---

## TODO-032 — Library card appreciation rate

**Status:** Open

**Show the home’s calculated appreciation %** on each library card (from `FinancialAssumptions.appreciation_pct` — FHFA/Zillow blend or Manual), so low-growth ZIPs are obvious in the list.

**Goals**
- Quiet caption or chip near the existing PITI/cash financial line (or meta chips) — e.g. `Appr. 2.4%/yr`.
- **Highlight under 3%** in amber (theme `#FFC107` / existing HOA-high pattern), not magenta risk unless design says otherwise.
- Hide or show `—` when financials/appreciation missing; don’t invent a fake rate on the card.
- Optional short source tooltip (`appreciation_source`) — nice-to-have, not required for v1.

**Non-goals:** Change blend math; add appreciation filters/sort (unless trivial later).

**Touch:** `app/ui/pages.py` (library cards), `app/ui/theme.py`, maybe `library_export.snapshot_from_property` if snapshot is the clean path, docs.
