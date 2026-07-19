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
| TODO-027 | Done | Remove Home Compare feature (library checkboxes + `/compare`) |
| TODO-028 | Done | Financials UX: collapse rarely-touched fields, per-field revert, hierarchy |
| TODO-029 | Done | Property header: show library nearby-signal icons (bottom-right, above tabs) |
| TODO-030 | Done | Gemini neighborhood prompts: pass exact home address (not only hood name) |
| TODO-031 | Done | Property page: lower visual weight of Edit listing details |
| TODO-032 | Done | Library card: show calculated appreciation %; amber if under 3% |
| TODO-033 | Done | Financials: replace field blurbs with clickable ? help (how defaults calculated) |
| TODO-034 | Done | Map Street View: negative-space polish and layout tweaks |
| TODO-035 | Done | Map / Street View: “Open in Google Earth” button |
| TODO-036 | Done | Library nearby icons: verify all five work; fix playground + shelter |
| TODO-037 | Done | Library card: remove unclear “Cash” from financial caption |
| TODO-038 | Done | Neighborhood: Assigned E/M/H schools (LAUSD GIS + SchoolDigger); removed Map Nearby schools panel |
| TODO-039 | Done | Library icon when home has no Central AC |
| TODO-040 | Done | Estimate utilities from provider + sqft + age |
| TODO-041 | Done | Map overlay: National Transportation Noise Map (BTS) |
| TODO-042 | Done | Library icon when location lacks broadband (FCC BDC; chip when env set) |
| TODO-043 | Done | Library icon: high building-permit activity within ~0.25 mi |
| TODO-044 | Done | Library card: rename appreciation label “Appr.” → “Growth” |
| TODO-045 | Done | Library/header street: −10% size; APT/UNIT → “#…” in smaller type |
| TODO-046 | Done | Library appreciation caption: lime/green when &gt; 6%/yr |
| TODO-047 | Open | Library nearby icons: click opens source URL in browser |
| TODO-048 | Open | Playground library icon: investigate low hit rate; widen radius and/or match criteria |

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
- **Map:** Schools toggle → markers within ~4 mi + legend. (The original "Nearby schools" distance-list panel was later removed by TODO-038, which moved per-home assigned-school detail to the Neighborhood tab.)
- Cache under `data/cache/schools_nces/` (~7d).

**Out of scope (v1):** paid ratings APIs, attendance-boundary polygons, walkability. (Attendance boundaries shipped for LAUSD in TODO-038.)

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
- Quiet `PITI $…/mo` caption on library cards when financials exist (`finance.summarize` via `app/core/library_export.py`); cash-to-close remains in export only.
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

**Status:** Done (2026-07-19)

**Remove** the side-by-side Compare flow shipped as TODO-018. Keep library financial captions + CSV/JSON export (TODO-016).

**Deleted / unwound**
- Library card checkboxes + **Compare** toolbar button + selection state.
- `/compare` page route and helpers (`compare_page`, `_compare_street`).
- `app/core/compare.py` + `tests/test_compare.py`.
- Docs / AGENTS / README mentions of Compare (product decision §8 + verify checklist).

**Kept:** Export menu, PITI card captions, rest of library chrome.

**Touch:** `app/ui/pages.py`, `app/main.py` (route import), `app/core/compare.py`, tests, `AGENTS.md`, `README.md`, this file.

---

## TODO-028 — Financials page cleanup (hierarchy + defaults)

**Status:** Done (2026-07-19)

**Problem:** The Financials tab lays out nearly every assumption at once (Your deal / Loan / Ownership / Buy vs rent tax knobs). Fields that rarely change compete with offer/down and the charts.

**Shipped**
1. **Primary surface** — always-visible **Your deal** (offer + down $) and **Buy vs rent** (comparable rent + rent control); hero monthly / charts stay above the fold.
2. **Collapsed** — **Loan**, **Ownership costs**, and **Advanced buy vs rent** live in quiet expansions (list/rate/term/closing; tax/insurance/HOA/maintenance/utilities; appreciation/invest/sell/budget/tax knobs).
3. **Per-field revert** — restart icon restores product/autofill baselines via `PropertyService.revert_financial_field` (clears Manual where applicable).

**Touch:** `app/modules/financial.py`, `app/ui/theme.py`, `property_service.revert_financial_field`, docs.

---

## TODO-029 — Nearby icons on property header

**Status:** Done (2026-07-19)

**Show the same library-card nearby proximity icons** (TODO-025: highway / transit / playground / grocery / shelter) on the **property page header**, bottom-right of the hero — **above the module tabs**.

**Shipped**
- Reuse cached `Property.nearby_signals` + shared `_render_nearby_signal_chips` (`hits_in_order`, tooltips, magenta risk / lime amenity).
- Position bottom-right of `.hb-property-hero` via theme padding; readable on bleed photo + scrim and beside mode.
- Same fixed order / thresholds as library; no new Map markers or filters.

**Touch:** `app/ui/pages.py` (property header), `app/ui/theme.py` (header icon placement), docs.

---

## TODO-030 — Gemini: exact home address (not only neighborhood)

**Status:** Done (2026-07-19)

**Problem:** Neighborhood Gemini (overview + things-to-do) prompts only got `{neighborhood}` + city/state. Answers were hood-generic and missed block-level context for the listing.

**Shipped**
- Overview + things-to-do prompts include `Property.address` plus neighborhood/city/state; walkshed / block-level framing anchors on the exact home.
- Cache keys bumped to `overview_v3|address|name|city|state` and `things_v3|address|name|city|state` so hood-only caches invalidate; Regenerate unchanged.

**Touch:** `app/core/gemini_neighborhood.py`, `property_service.py`, tests, `AGENTS.md` §6.

---

## TODO-031 — Quieter “Edit listing details”

**Status:** Done (2026-07-19)

**Problem:** On the property page, **Edit listing details** sits as a full-width expansion under the header actions and competes with Photos / Map / Neighborhood / Financials.

**Shipped**
- Moved inside the property hero content, below Refresh / Gemini actions, as a dense collapsed secondary control.
- Muted chrome via `.hb-edit-listing-expansion` (greyed label/icon; full opacity on hover/focus).
- Kept all existing edit fields + Save behavior.

**Touch:** `app/ui/pages.py`, `app/ui/theme.py`, docs.

---

## TODO-032 — Library card appreciation rate

**Status:** Done (2026-07-19)

**Show the home’s calculated appreciation %** on each library card (from `FinancialAssumptions.appreciation_pct` — FHFA/Zillow blend or Manual), so low-growth ZIPs are obvious in the list.

**Shipped**
- `LibraryFinancialSnapshot.appreciation_pct` / `appreciation_source` via `snapshot_from_property`; quiet `Growth N%/yr` beside PITI on library cards.
- Under 3% uses amber `.hb-appr-low`; over 6% uses lime `.hb-appr-high`; 3–6% neutral; hidden when no financials / missing appreciation.
- Optional source tooltip from `appreciation_source`.

**Touch:** `app/core/library_export.py`, `app/ui/pages.py`, `app/ui/theme.py`, docs.

---

## TODO-033 — Financials: ? help instead of inline descriptions

**Status:** Done (2026-07-19)

**Problem:** Financials fields carry a lot of always-visible helper copy (source captions, “default 10%”, tax/CG/SALT explainers). That adds noise next to the numbers.

**Shipped**
- Low-opacity `?` (`help_outline`) beside each field label; tooltip explains how the default/autofill is calculated (`_FIELD_HELP` in `financial.py`).
- Short live **source captions** kept under autofilled values (PMMS, tax/insurance/maint/utilities/rent/appreciation).
- Coordinates with TODO-028 hierarchy (help + revert survive collapse).

**Touch:** `app/modules/financial.py`, `app/ui/theme.py`, docs.

---

## TODO-034 — Street View negative-space polish ✅ Done

**Status:** Done

**Done:** Removed the forced `min-height` shell that left black gutter under the scaled `svembed`; `.homebuy-sv` is 16:9 with `max-height: min(42vh, 480px)` and width capped when the height binds. Dense expansion (`.hb-sv-panel`), tighter action-row gap, quieter unpinned hint. Still free `svembed` only.

**Touch:** `app/modules/street_view.py`, `app/ui/theme.py`, docs.

---

## TODO-035 — Open in Google Earth ✅ Done

**Status:** Done

**Done:** “Open in Google Earth” dense neo button beside Maps / Street View when the pin exists. Deep link `https://earth.google.com/web/@{lat},{lng},100a,1000d,35y,0h,0t,0r` (new tab). No API key / embed.

**Touch:** `app/modules/street_view.py`, docs.

---

## TODO-036 — Library nearby icons: verify + fix playground / shelter

**Status:** Done (2026-07-19)

**Problem:** Library proximity chips (TODO-025) — highway / transit / playground / grocery / shelter — need an end-to-end check. **Playground** and **homeless shelter** distance icons often don’t appear even when amenities exist nearby.

**Shipped**
- Root causes: Overpass `out geom` ways lacked `center`, so polygon playgrounds/shelters/grocery buildings were dropped; Places empty results overwrote good OSM hits; shelter Places used a broken `|` keyword OR and a too-tight 0.25 mi gate.
- Fixes: `out center geom tags` + geometry fallback for all ways; playground also matches `leisure=park`+`playground=yes` and relations; shelter accepts semicolon `social_facility:for` lists + `homeless=yes`; Places uses three separate keyword searches and keeps the nearer of OSM vs Places; thresholds retuned (playground ≤0.75 mi, shelter ≤0.5 mi).
- Tests cover way-without-center, shelter tag variants, Places/OSM merge, and bus-stop weather shelter exclusion.
- Documented final thresholds in AGENTS §8a.
---

## TODO-037 — Library card: drop “Cash” caption

**Status:** Done (2026-07-19)

**Remove “Cash $…” from the library card financial line.** Label is unclear (cash-to-close vs cash left / reserves). Keep **PITI $…/mo** (and other card chrome).

**Kept:** `cash_to_close` in Financials tab and CSV/JSON export.

**Touch:** `app/ui/pages.py` (`_library_financial_caption`), `AGENTS.md` / `README` library checklist wording.

---

## TODO-038 — Assigned schools on Neighborhood (LAUSD + free CA Dashboard/Niche)

**Status:** Done (2026-07-18); quality layer swapped off SchoolDigger the same day (see below)

**Show the Elementary / Middle / High schools a home is zoned for** on the Neighborhood tab, instead of only a "nearby NCES points" list on the Map.

**Shipped**
- `app/core/school_zones.py`: point-in-polygon (`point_in_ring`/`point_in_polygon`) against **LAUSD** attendance ArcGIS layers (elementary/middle/high); resolves each zone's school **name** via layer-0 school points inside the polygon (attendance layers carry a key but no name). `resolve_assigned(lat, lng)` → `status` `ok`/`outside`/`gap`/`no_pin`/`error`, cached ~7d.
- `app/core/school_quality.py`: free, no-key enrich — **CA School Dashboard** color badge (Blue/Green/Yellow/Orange/Red) looked up by CDS code from the free CDE Academic Indicator downloadable data (cached ~30d), plus **Niche** parent-review + **CA Dashboard** report-page deep links; always runs, never gated on a key, never raises.
- `app/modules/neighborhood_reviews.py`: **Assigned schools** section (three cards, cyan/magenta/lime accents) before the Gemini overview; resolved off the event loop via `resolve_assigned_schools_job` (`ui_jobs.py`) with instant loading placeholders; honest empty-state captions (no pin / outside LAUSD / boundary gap).
- `app/modules/map_view.py`: removed the old **Nearby schools** distance-list panel; Schools layer toggle, NCES markers, and legend are unchanged.

**Quality-layer swap (2026-07-18):** SchoolDigger is a paid API and SchoolScope's public API isn't usable (403/"coming soon"), so `app/core/schooldigger.py` was deleted and replaced by `app/core/school_quality.py` (free CA Dashboard + Niche, no API keys). `SCHOOLDIGGER_*` removed from `.env.example`.

**Non-goals (v1):** districts other than LAUSD; campus photos; "nearest school" proximity guessing (attendance boundaries only).

**Touch:** `app/core/school_zones.py`, `app/core/school_quality.py`, `app/core/ui_jobs.py`, `app/modules/neighborhood_reviews.py`, `app/modules/map_view.py`, `app/ui/theme.py`, `.env.example`, `tests/test_school_zones.py`, `tests/test_school_quality.py`, `tests/test_assigned_schools_ui.py`, docs.

---

## TODO-039 — Library icon: no Central AC

**Status:** Done (2026-07-19)

**Show a library-card proximity-style risk icon** when the listing does **not** have Central AC (common LA buyer flag — window/wall units only, evaporative, none, etc.).

**Shipped**
- Scrape cooling from Zillow (`resoFacts.cooling` / `cooling` / regex fallback) into `ListingDetails.cooling` + `has_central_ac` (`app/core/zillow_listing.py`).
- Persist `Property.cooling` + nullable `Property.has_central_ac`; apply on add / Refresh listing details.
- Classification (`app/core/listing_signals.py`): chip only when clearly **no** central AC (window/wall/evaporative/swamp/ductless/mini-split/none); unknown/ambiguous → no chip; has central → no chip.
- Helpers: `classify_has_central_ac`, `central_ac_risk_entry`, `listing_risk_chips` — library + property header render magenta `ac_unit` chip in the nearby-icons row (`pages.py`).

**Touch:** `zillow_listing.py`, `listing_signals.py`, `models.py`, `db.py`, `property_service.py`, `pages.py`, `tests/test_listing_signals.py`, docs.

---

## TODO-040 — Estimate utilities (provider + sqft + age)

**Status:** Done (2026-07-19)

**Estimate monthly utilities** for a home from **utility provider**, **sqft**, and **year built / age**.

**Shipped**
- `app/core/utilities.py` + `app/data/utility_providers.json`: LADWP vs SCE electric + SoCalGas gas heuristics from city/ZIP (LA-area); Default fallback elsewhere.
- Formula: `(electric_psf×sqft + gas_base + gas_psf×sqft) × age_factor + water/trash`; assumes ~1800 sqft when size missing.
- Persist `monthly_utilities` + `utilities_source` on `FinancialAssumptions`; autofill on add/sync/`ensure_financial` unless Manual; never breaks add-home.
- Shown under collapsed **Ownership costs**; included in **hero monthly / pie / buy-vs-rent buyer housing cost** (same path as maintenance — ownership cash cost, not PITI).

**Decision:** Utilities count toward ownership display cash cost (`monthly_owner_total` and buy-vs-rent budget surplus) alongside maintenance; mortgage PITI math unchanged.

**Touch:** `utilities.py`, data table, `models.py` / `db.py`, `property_service.py`, `finance.py`, `financial.py`, tests, docs.

---

## TODO-041 — National Transportation Noise Map (BTS) overlay

**Status:** Done (2026-07-19)

**Shipped**
- Exclusive Map **Noise** toggle: ArcGIS XYZ tiles from `Hosted/NTAD_Noise_2020_CONUS_Aviation_Road_Rail` (`app/core/bts_noise.py`) — TilesOnly (no WMS).
- Status disclaimer: screening/trend, not parcel-precise.
- Legend swatches + neo layer button.

**Touch:** `bts_noise.py`, `map_view.py`, docs.

---

## TODO-042 — Library icon: missing broadband (FCC BDC)

**Status:** Done (2026-07-19) — chip appears when `FCC_BDC_USERNAME` + `FCC_BDC_HASH` (or `FCC_BDC_HASH_VALUE`) are set; without credentials status stays unknown (no chip).

**Risk rule:** flag only when **no fixed terrestrial** providers (DSL/copper, cable, fiber, fixed wireless). DSL/cable alone does **not** flag. Satellite-only → risk. Unknown / no credentials / fetch error → no chip.

**Shipped**
- `app/core/fcc_broadband.py` — credentials gate; soft BDC `listAsOfDates` ping; point path = FCC Geo block FIPS + Living Atlas BDC block UniqueProviders*; cache `data/cache/fcc_broadband/`; never fails add-home.
- `Property.broadband_status` + `broadband_at`; migrate in `db.py`; compute on add / post-geocode; stale refresh via `refresh_stale_broadband_status_job`.
- Helpers: `chip_spec_for` / `tooltip_for`; included in `listing_risk_chips` → library + property header.
- Tests: `tests/test_fcc_broadband.py` (mocked HTTP).
- `.env.example`: `FCC_BDC_USERNAME` + `FCC_BDC_HASH`.

**Research:** `docs/RESEARCH.md` § Missing broadband / FCC BDC.

**Non-goals:** Full ISP comparison UI; Map choropleth; speed-test measurement; Fabric-licensed BSL-exact lookup.

**Touch:** `fcc_broadband.py`, models/db, property_service, listing_signals, ui_jobs, pages, tests, docs.

---

## TODO-043 — Library icon: high permit activity (~0.25 mi)

**Status:** Done (2026-07-19)

**Shipped**
- Research table in `docs/RESEARCH.md` (LA `pi9x-tg5x` / Seattle `76t5-zqzr` / Austin `3syk-w9eu`).
- `app/core/permits_nearby.py`: `within_circle` ~0.25 mi, 24-month window; **high activity ≥ 8**; cache `data/cache/permits/`.
- Persist `permits_activity` + `permits_activity_at`; refresh on add/geocode; library stale refresh via `refresh_stale_permits_activity_job`.
- Amber `.hb-nearby-chip--amber` via `chip_spec_for` → `_extra_signal_chips` on library cards + property header.
- Tests: `tests/test_permits_nearby.py`.

**Non-goals:** Full permit browser UI; Map overlay of every permit; national coverage day one.

**Touch:** `permits_nearby.py`, models/db, property_service, ui_jobs, pages, theme, tests, docs.

---

## TODO-044 — Library card: “Growth” instead of “Appr.”

**Status:** Done (2026-07-19)

**Rename** the library-card appreciation caption from `Appr. N%/yr` to **`Growth N%/yr`** (same value; amber &lt; 3% / lime &gt; 6% via TODO-046).

**Touch:** `app/ui/pages.py` (`_library_appreciation_caption`), docs/AGENTS wording if they say “Appr.”.

---

## TODO-045 — Compact street + unit on library / header

**Status:** Done (2026-07-19)

**Problem:** Long Akira street lines (with `APT` / `UNIT` / Suite condo markers) overflow or crowd library cards at narrower widths.

**Shipped**
1. Library/header street type ~10% smaller (`--hb-library-address-size: clamp(1.215rem, 3.6vw, 2.25rem)`).
2. Display-only unit normalize (`APT`/`APARTMENT`/`UNIT`/`STE`/`SUITE`/`#…` → `#…`) via `_split_street_unit` — stored `Property.address` unchanged.
3. Unit segment in `.hb-library-unit` at `0.75em` (~25% smaller) via `_render_street_address` on library cards and property header.

**Touch:** `app/ui/pages.py`, `app/ui/theme.py`, `tests/test_library_street_display.py`, docs.

---

## TODO-046 — Lime highlight when appreciation &gt; 6%/yr

**Status:** Done (2026-07-19)

**Problem:** Library cards already amber-highlight low appreciation (`&lt; 3%/yr`, TODO-032). High growth rates have no positive counterpart.

**Shipped**
1. Annual appreciation **&gt; 6%/yr** → lime `.hb-appr-high` (`--hb-neon-3` / `#B8FF3C`).
2. Keep amber `.hb-appr-low` for **&lt; 3%/yr**.
3. **3–6% inclusive** stays neutral (`_library_appreciation_tone_class`).

**Bands**

| Rate | Style |
|------|--------|
| `&lt; 3%` | Amber (existing) |
| `3%`–`6%` inclusive | Neutral |
| `&gt; 6%` | Lime / green |

**Touch:** `app/ui/pages.py`, `app/ui/theme.py`, docs.

---

## TODO-047 — Library nearby icons: click → source in browser

**Status:** Open

**Problem:** Library (and header) nearby-signal chips stop propagation so they do not open the property card, but a click does nothing useful — only hover shows distance + name. Users want a way to inspect the hit.

**Goals**
1. Clicking a nearby-signal chip (highway / transit / playground / grocery / shelter) opens an **external browser tab/window** to a **source URL** for that hit — not the property page.
2. Chip click must still **not** navigate the library card underneath (keep `stopPropagation`).
3. Pick a sensible deep link per signal / provider when implementing (e.g. Google Maps place or lat/lng query; OSM node/way page; Places URL when `place_id` exists). Prefer the provider that produced the hit.
4. Tooltip / title can stay; **v1 is click → source URL**.

**Likely approach**
- Enrich cached `nearby_signals` JSON with enough fields to build links (`lat`/`lng`, `name`, `osm_id` / OSM type, `place_id`, etc.) if not already present.
- Wire chip click in `pages.py` (`_render_nearby_signal_chips` / library + header) to `ui.navigate.to(url, new_tab=True)` or equivalent.

**Non-goals:** In-app detail panel/modal; Map markers for the hit; changing distance thresholds or chip styling.

**Touch:** `app/ui/pages.py` (chip click), possibly `app/core/nearby_signals.py` + cached JSON shape, tests, docs.

---

## TODO-048 — Playground library icon: low hit rate (investigate then tune)

**Status:** Open

**Problem:** Library playground proximity chips still feel sparse after TODO-036 (radius raised to **0.75 mi**; Overpass center/geom + `leisure=park`+`playground=yes`). Users expect the icon more often.

**Goals**
1. **Investigate first** (not a blind radius bump): sample homes where a playground is nearby in Maps/OSM but the chip is missing; compare Overpass tags (`leisure=playground` vs parks with play equipment / other common tags), whether Places fallback exists for playground (today Places only refines grocery + shelter), and whether **0.75 mi** is below user expectation.
2. Ship a **measured** change: increase distance and/or widen what counts as a playground (OSM tags and/or optional Places), with tests covering the new match rules.
3. Update AGENTS §8a thresholds / match criteria when done.

**Likely approach**
- Audit `app/core/nearby_signals.py` playground query + thresholds vs real OSM coverage around existing library pins.
- Decide: larger radius, broader tags (e.g. more park/play-equipment patterns), and/or Places Nearby Search for playground — prefer evidence over guesswork.

**Non-goals:** Changing other nearby signals’ thresholds in the same pass unless investigation proves a shared bug; Map markers for playgrounds; TODO-047 click-to-source.

**Touch:** `app/core/nearby_signals.py`, tests, `AGENTS.md` §8a, docs.

**Related:** TODO-025 (shipped), TODO-036 (shipped — radius/geom/tag fixes; hit rate still low).
