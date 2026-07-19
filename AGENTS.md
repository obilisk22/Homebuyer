# Homebuy — Agent Continuity Guide

> Read this first when starting a new agent session on this project.
> Last updated: 2026-07-19 (TODO-044/045/046: Growth caption, compact street+#unit, lime &gt;6%)



## What this is

**Homebuy** is a personal Python web app for researching homes linked from Zillow. Paste a Zillow listing URL → save the home → dive deeper than Zillow’s UI (photos, map, street view, financials). Built to be **module-extensible**.

| | |
|---|---|
| **Path** | `C:\Users\hheaf\Projects\homebuy` |
| **Stack** | Python 3.12, NiceGUI, SQLAlchemy + SQLite, Plotly, Leaflet, curl_cffi |
| **UI** | Dark cyberpunk theme — Creato Display body/prices + Akira Expanded street/brand; cyan emission hierarchy |
| **App URL** | http://127.0.0.1:8080 |

## How to run (Windows)

PowerShell **blocks** `Activate.ps1` (execution policy). Always use the venv interpreter directly:

```powershell
cd C:\Users\hheaf\Projects\homebuy
.\.venv\Scripts\python.exe -m app.main
```

Or double-click `run.bat`.

```powershell
# Tests
.\.venv\Scripts\pytest.exe -q

# Restart: stop only the process whose command line contains app.main on port 8080, then start again
```

Python install (if needed): `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`

## Git — saving progress

| | |
|---|---|
| **Local repo** | `C:\Users\hheaf\Projects\homebuy` (branch `main`) |
| **GitHub remote** | https://github.com/obilisk22/Homebuyer.git (`origin`) |
| **Author (this repo)** | Harrison Moore \<hheafnermoore@gmail.com\> |

A Git repository lives in this folder. Commits save history locally; **`git push`** copies them to GitHub.

| Perforce idea | Git idea |
|---------------|----------|
| Depot / workspace | Repository (this folder + `.git/`) |
| Changelist | Commit (a snapshot + message) |
| `p4 submit` | `git commit` (local) then `git push` (to GitHub) |
| Pending files | Working tree + staging area (`git add`) |

**What is NOT in Git** (by design, see `.gitignore`): `.venv/`, `.env`, `data/homebuy.db`, downloaded photos under `data/uploads/`. Your code and docs *are* saved.

**Auto-commit (local only):** a project Cursor `stop` hook (`.cursor/hooks.json` → `.cursor/hooks/auto-commit.cmd`) commits dirty work when an agent turn finishes. It never pushes — upload to GitHub is still a manual `git push`. Empty commits and secrets/`.env`/`data/`/`.venv` are skipped.

### Everyday commands (run from project folder)

```powershell
cd C:\Users\hheaf\Projects\homebuy

# What changed?
git status

# Stage everything intentional, then snapshot locally
git add -A
git status
git commit -m "Short description of why you changed things."

# Upload to GitHub (after a commit)
git push

# Browse history
git log --oneline -10
```

When an agent finishes a feature: commit if the user asked to save/commit; push if the user asked to push; always update `AGENTS.md` + `README.md`.

## User preferences (important)

- **Bias toward spinning up new agents** for parallel work so the main chat context stays lean.
- Prefer **agents for research + feature chunks**; coordinate file ownership when two agents run in parallel.
- Do **not** use paid Google Maps Embed API for Street View — free `output=svembed` iframe only.
- Zillow-centric: library add form is **Zillow URL only** (no separate address field). Address is derived from the URL slug and/or listing HTML.
- Aesthetic: sleek dark cyberpunk — avoid generic purple-on-white / cream-terracotta AI defaults.

## Architecture

```
User → NiceGUI (app/ui/pages.py)
         → module_registry (app/modules/*)
         → PropertyService + SQLite (data/homebuy.db)
```

### Extending with a module

Create `app/modules/my_feature.py`:

```python
from app.core.module_registry import ModuleSpec
from nicegui import ui

def render(prop, container: ui.element) -> None:
    with container:
        ui.label(prop.address)

MODULE = ModuleSpec(id="my_feature", title="My Feature", order=50, render=render)
```

Restart the app — the tab appears automatically.

### Key files

| Area | Path |
|------|------|
| Entry | `app/main.py` |
| Library + property pages | `app/ui/pages.py` |
| Theme | `app/ui/theme.py` |
| Models / migrate | `app/core/models.py`, `app/core/db.py` |
| CRUD / Zillow add | `app/core/property_service.py` |
| Long UI I/O workers (`run.io_bound`) | `app/core/ui_jobs.py` |
| Geocode (unit stripping + fallbacks) | `app/core/geocode.py` |
| Photo import | `app/core/zillow_photos.py` |
| Listing fields extract | `app/core/zillow_listing.py` |
| Neighborhood + Gemini overview / things-to-do | `app/core/neighborhood.py`, `app/core/gemini_neighborhood.py` |
| Financials Gemini commentary | `app/core/gemini_financial.py` |
| Maintenance / repair estimate | `app/core/home_maintenance.py`, `app/data/home_maintenance_state_index.json` |
| Utilities estimate (provider × sqft × age) | `app/core/utilities.py`, `app/data/utility_providers.json` |
| Mortgage rates (Freddie Mac PMMS) | `app/core/mortgage_rates.py` |
| Library thumbnail pick | `app/core/thumbnail.py` |
| Library nearby proximity icons (OSM Overpass + optional Places) | `app/core/nearby_signals.py` |
| Listing risk chips (no Central AC) | `app/core/listing_signals.py` |
| Nearby building-permit activity (Socrata SODA; LA/Seattle/Austin) | `app/core/permits_nearby.py` |
| FCC missing-broadband risk (BDC credentials + Living Atlas block) | `app/core/fcc_broadband.py` |
| Assigned schools (LAUSD attendance PIP + name resolve) | `app/core/school_zones.py` |
| CA Dashboard color + Niche deep link (free, no keys) | `app/core/school_quality.py` |
| Mortgage math + buy vs rent projection | `app/core/finance.py` |
| Library financial snapshot + CSV/JSON export | `app/core/library_export.py` |
| FHFA ZIP HPI (~10y CAGR, no API key) | `app/core/fhfa_hpi.py` |
| Map overlays | `app/core/{census_acs,fema_flood,crime_socrata,crime_density,zoning_gis,schools_nces,wildfire_whp,air_quality,redfin_sales,overlay_cache}.py` |
| Dark basemap | `app/core/map_basemap.py` (CARTO `dark_all` after `ui.leaflet`) |
| Modules | `app/modules/{gallery,map_view,neighborhood_reviews,financial}.py` (+ `street_view.py` helpers, no tab) |
| Env template | `.env.example` |

### Data model (high level)

**Property:** `address`, `zillow_url`, `list_price`, `beds`, `baths`, `sqft`, `hoa_fee`, `year_built`, `home_type`, `cooling`, `has_central_ac`, `city`, `state`, `zip_code`, `latitude`, `longitude`, `thumbnail_photo_id`, `thumbnail_locked`, `notes`, `nearby_signals`, `nearby_signals_at`, `permits_activity`, `permits_activity_at`, `broadband_status`, `broadband_at`, `neighborhood_name`, `neighborhood_source`, `neighborhood_override`, `neighborhood_notes`, `neighborhood_gemini`, `neighborhood_gemini_for`, `neighborhood_things_to_do`, `neighborhood_things_to_do_for`, `financial_gemini`, `financial_gemini_for`

**Photo:** `path`, `source_url`, `caption`, `sort_order`

**FinancialAssumptions:** `list_price`, `offer_price`, loan/ownership fields (math uses **offer** if set, else list). Legacy `purchase_price` kept in sync. `property_tax_source` / `insurance_source` / `interest_rate_source` record how tax / insurance / rate were resolved (e.g. `Zillow`, `Freddie Mac PMMS 30-yr FRM · …`) and are shown as UI captions. Buy-vs-rent: `monthly_rent` (default **5300** when no Zillow rent), `rent_source` (e.g. `Zillow` / `Default` / `Manual`), `rent_control`, `rent_growth_pct`, `rent_growth_source`, `appreciation_pct`, `appreciation_source`, `appreciation_fhfa_pct`, `appreciation_zillow_pct` (FHFA/Zillow components kept for chart captions even when appreciation is manually overridden), `invest_return_pct` (default 10), `selling_cost_pct` (default 6), `monthly_maintenance` (age-blend autofill; default 0 until sync), `maintenance_source` (e.g. `Estimated: age blend · CA×1.15` / `Manual`), `monthly_utilities` (provider × sqft × age; default 0 until sync), `utilities_source` (e.g. `Estimated: LADWP+SoCalGas · age×1.15` / `Manual`), `monthly_budget` (default **13000**), `marginal_tax_pct` (default **41** CA MFJ-style), `cg_tax_pct` (default **24**), `cg_exclusion` (default **500000**), `salt_cap` (default **10000**).

SQLite migrations are lightweight `ALTER TABLE` helpers in `app/core/db.py` (`_migrate_sqlite`).

## What’s done

- [x] Project bootstrap, NiceGUI shell, module registry
- [x] Add home from Zillow URL only; import photos + listing details
- [x] Photos gallery + lightbox; exterior-ish library thumbnails
- [x] Gallery UX: denser larger tiles; no per-photo Remove; Photos tab is view/pin only (import on add only)

- [x] Map geocode (Nominatim default; optional Google key); unit/apt address fix
- [x] Street View free desktop 16:9 panel (no Cloud billing)
- [x] Financials: offer vs list, PITI + PMI, neon Plotly charts + Gemini opinion from Zillow URLs (URL context; `fin_v4` cache)
- [x] Library search/filters (price, beds, city/address)
- [x] Cyberpunk dark theme
- [x] Add-home is Zillow URL only (address from listing/URL)
- [x] Initial Git commit + push to https://github.com/obilisk22/Homebuyer (`main`)
- [x] Neighborhood Reviews: Zillow neighborhood name + Gemini overview + things-to-do list + deep links/notes
- [x] Map overlays: FEMA flood WMS + Zoning (LA City/SM/County; WS-safe slim/merge by zone_code) + full ACS tract set (income, home value, median age, avg kids, % owner-occupied, year built, gross rent, % bachelor's+) + LA County crime (LAPD Socrata + Santa Monica CKAN) + Seattle hex density choropleth + NCES schools + USFS wildfire WHP + Open-Meteo AQI hex + Redfin ZIP/ZCTA sale choropleth
- [x] Street View folded into Map tab (map on top, free svembed below; no standalone SV tab)
- [x] Map tab Direction 1 polish: CARTO dark basemap, compact layer bar, taller map, quieter status, Pin tools + collapsible Street View below map
- [x] TODO-034 / TODO-035 (2026-07-19): Street View dense 16:9 panel (no min-height gutter) + Open in Google Earth deep link
- [x] Map fullscreen control (leaflet.fullscreen near zoom; survives redraw)
- [x] Richer Zillow listing scrape: beds, price, sqft, HOA, year built, home type (library + header + edit)
- [x] Library visual refresh + iteration 2: list cards (~180×135 thumb), neon price, chips + amber HOA ≥$400, notes teaser, ⋮ menu (Zillow/Delete), sort + filter active count, compact Add when nonempty; lockable library thumb from Photos + stronger exterior auto-pick
- [x] TODO-025 Library nearby-signal icons (2026-07-18): OSM Overpass for highway (nearest way vertex ≤800 ft) / transit / playground / grocery / shelter; Google Places Nearby Search for grocery + shelter when `GOOGLE_MAPS_API_KEY` set; cached JSON on `Property` plus ~7d raw provider cache; soft neo thumbnail chips (magenta risks, lime amenities) with distance/name tooltips; compute on add/post-geocode + post-paint best-effort stale refresh (≤3, ~30d) on library load
- [x] Visual foundation (2026-07-18): hierarchy-through-emission; Creato + Akira self-host; library street hero + stretch thumb; page chrome (title/Add/Filter/empty) matched to cards
- [x] Property tab chrome (2026-07-18): property header (Akira street + chips), Photos/Map/Neighborhood/Financials titles/hints/empty states + dense controls; Leaflet/Plotly/svembed unchanged
- [x] Property header library photo (2026-07-18): full-bleed + scrim by default (`PROPERTY_HEADER_PHOTO_MODE = "bleed"`); flip to `"beside"` for card-style thumb
- [x] Dark neumorphism on buttons + tabs (2026-07-18): extruded/inset soft faces; cyan reserved for primary CTA + active tab
- [x] Map overlay neo toggles (2026-07-18): checkbox row → label-only neo buttons with emissive glow when on
- [x] Audit polish batch (2026-07-18): Financials 2×2 form grid; library-only card hover; short Map overlay labels + toggle `--on` fix; Quasar greys → `hb-*`; neo Photos lightbox + actions above grid; Filter Enter/debounce + Apply; clickable brand / no redundant Back; library responsive clamp/stack; in-tab Gemini Ask/Regenerate (Financials + Neighborhood)
- [x] TODO-006 codebase cleanup (2026-07-18): dead helpers removed, single Zillow HTML fetch on add, batched photo import, fewer redundant DB loads, overlay cache prune on miss, lazy Plotly import — features unchanged
- [x] TODO-011 Financials autofill (2026-07-18): list price/HOA/tax/insurance filled from the Zillow listing on add/refresh, with a tax chain (Zillow → assessed×rate → ACS county rate) and a state avg-premium insurance fallback; source captions shown under the Ownership inputs; down/term/closing never overwritten
- [x] Prefer Zillow insurance scrape (2026-07-18): wider extract for `annualHomeownersInsurance` + alternate/monthly keys, deep-walk + regex; state table only when listing omits the field
- [x] TODO-012 Mortgage rate autofill (2026-07-18): Interest rate filled from Freddie Mac PMMS 15/30 averages by loan term (closer product); caption under rate; Manual override when edited; Term change refreshes matching average
- [x] Financials deal UX (2026-07-18): Your deal = offer + down in dollars with &lt;20% amber PMI warning; Assumptions quieter below
- [x] Financials buy vs rent + invest chart (2026-07-18): Plotly dual-line (buy net worth vs rent + invest) + monthly mix pie only (loan balance / cumulative P&I charts removed); FHFA ZIP5 ~10y CAGR + Zillow decade % blended (default 3% if both missing); rentZestimate prefill (default **$5300**/mo / `Default` when missing); editable invest return / sell cost / monthly maintenance; loan terms never overwritten
- [x] TODO-017 Buy-vs-rent editable what-ifs (2026-07-18): invest return %/yr, sell cost %, optional monthly maintenance persisted on `FinancialAssumptions`; charts use live values
- [x] TODO-026 Connection lost fix (2026-07-18): long UI I/O via `run.io_bound` + `app/core/ui_jobs.py` (add-home, Map overlays, Gemini)
- [x] Buy vs rent two-way $13k surplus + tax/CG (2026-07-18): shared budget invest on both paths; interest+SALT shield @41%; MFJ $500k CG exclusion @24%; editable assumptions
- [x] Financials rent growth + rent control (2026-07-18): **Rent control** checkbox beside comparable rent → **2%/yr**; unchecked → ACS county **B25064** ~5y CAGR via `county_median_rent_cagr` (needs `CENSUS_API_KEY`, county from pin); **3%** / `Default` on miss; rent rises in projection (`rent_growth_pct`); owner **PITI flat**; captions under rent + chart; Manual override clears control
- [x] FHFA ZIP5 parser header fix (2026-07-18): scans past workbook title/notes for ZIP + year + HPI-level headers; exact `HPI` is preferred over Annual Change (%); regression test covers the real workbook layout
- [x] Cleanup sweep #2 (2026-07-18): Gemini Ask uses warm cache without re-calling API; deduped financial sync on add/refresh; docs aligned to overlays/Census/Gemini env vars
- [x] TODO-016 Library financial snapshots + export (2026-07-18): quiet PITI caption on cards; CSV/JSON export (`library_export.py`)
- [x] TODO-027 Remove Home Compare (2026-07-19): library checkboxes, Compare button, `/compare` route, `compare.py` + tests deleted; Export + PITI captions kept
- [x] TODO-013 Schools (2026-07-18): NCES public school points within ~4 mi (CCD primary; EDGE opengis fallback) + Map Schools toggle + legend
- [x] TODO-020 Wildfire + AQI (2026-07-18): USFS WHP WMS + Open-Meteo US AQI hex choropleth
- [x] TODO-021 Redfin sale choropleth (2026-07-18): ZIP median → ZCTA join
- [x] Assigned schools on Neighborhood (2026-07-18): **Elementary / Middle / High** cards resolved via **LAUSD attendance-boundary point-in-polygon** (`app/core/school_zones.py`; ArcGIS `LAUSD_Schools` MapServer layers 4/5/6) + name resolve via layer-0 school points inside each zone; free **CA School Dashboard** color badge + **Niche** parent-review deep link (`app/core/school_quality.py`, no API keys); honest empty states (no pin / outside LAUSD / boundary gap); moved off the event loop via `resolve_assigned_schools_job` (`ui_jobs.py`). Map **Nearby schools** panel removed — Schools layer toggle/markers/legend on the Map tab are unchanged.
- [x] SchoolDigger → free quality layer swap (2026-07-18): replaced the paid SchoolDigger API with `app/core/school_quality.py` — CA School Dashboard performance-level color (Blue/Green/Yellow/Orange/Red) looked up by CDS code from the free CDE Academic Indicator downloadable data (ELA, All Students, school-level rows; cached ~30d under `data/cache/ca_dashboard/`, same one-time-download pattern as Redfin) + a Niche parent-review deep link + a CA Dashboard report-page link. No API keys; `SCHOOLDIGGER_*` removed from `.env.example`.
- [x] TODO-043 permit activity (2026-07-19): Socrata SODA within_circle ~0.25 mi for LA / Seattle / Austin; ≥8 permits in 24 mo → amber `construction` chip on library + header; stale refresh on library paint
- [x] TODO-028 / TODO-033 / TODO-040 Financials UI (2026-07-19): primary **Your deal** + rent/rent control; **Loan** / **Ownership** (incl. **utilities**) / **Advanced buy vs rent** behind expansions; per-field revert via `revert_financial_field`; low-opacity `?` help tooltips; utilities in hero/pie/buy-vs-rent cash cost
- [x] TODO-037 / TODO-032 / TODO-031 / TODO-029 (2026-07-19): library PITI-only caption + appreciation % (amber &lt;3%); quieter Edit listing details; property-header nearby chips
- [x] TODO-044 / TODO-045 / TODO-046 (2026-07-19): Growth caption; street −10% + smaller `#unit`; lime Growth when &gt;6%/yr
- [x] TODO-039 no Central AC chip (2026-07-19): scrape cooling → `Property.cooling` / `has_central_ac`; magenta risk chip via `listing_signals.listing_risk_chips` on library + property header
- [x] TODO-042 missing broadband chip (2026-07-19): optional `FCC_BDC_*` credentials; FCC Geo + Living Atlas BDC block UniqueProviders*; magenta `wifi_off` when no fixed terrestrial service; unknown/no credentials → no chip

## In progress / next (as of last session)

| ID | Status | Notes |
|----|--------|-------|
| `TODO-002` | **Won't fix** | Umbrella closed; flood/zoning/ACS/crime + 013/020/021 shipped |
| `TODO-015` / `022` / `023` | **Won't fix** | Pipeline status, closing checklist, document vault — not pursuing |
| `TODO-013` / `020` / `021` | **Done** | Schools (NCES map points), wildfire/AQI, Redfin ZIP sales |
| — | **Done** | Assigned schools (LAUSD GIS + free CA Dashboard/Niche) on Neighborhood; Map Nearby schools panel removed |
| `TODO-016` | **Done** | Library snapshots/export |
| `TODO-017` | **Done** | Buy-vs-rent editable invest return / sell cost / maintenance |
| `TODO-026` | **Done** | Connection lost — `run.io_bound` + `ui_jobs.py` |
| `TODO-027` | **Done** | Removed Home Compare (checkboxes + `/compare`) |
| `TODO-028` | **Done** | Financials UX — primary deal/rent; Loan/Ownership/Advanced expansions; per-field revert |
| `TODO-029` | **Done** | Property header nearby icons (library chips, above tabs) |
| `TODO-030` | **Done** | Gemini neighborhood — pass exact home address |
| `TODO-031` | **Done** | Quieter / relocate Edit listing details |
| `TODO-032` | **Done** | Library card appreciation % (amber if &lt; 3%) |
| `TODO-033` | **Done** | Financials — ? help tooltips for default/autofill explainers |
| `TODO-034` | **Done** | Street View negative-space polish on Map tab |
| `TODO-035` | **Done** | Open in Google Earth button |
| `TODO-036` | **Done** | Nearby icons — verify all five; fix playground + shelter |
| `TODO-037` | **Done** | Library card — remove unclear Cash caption |
| `TODO-039` | **Done** | Library icon when home has no Central AC |
| `TODO-040` | **Done** | Utilities estimate (provider × sqft × age) + Ownership UI |
| `TODO-041` | **Done** | Map overlay — BTS National Transportation Noise Map |
| `TODO-042` | **Done** | Missing broadband chip (FCC BDC credentials + Living Atlas block) |
| `TODO-043` | **Done** | High permit activity amber chip (LA / Seattle / Austin) |
| `TODO-044` | **Done** | Library card — rename “Appr.” → “Growth” |
| `TODO-045` | **Done** | Street address −10%; APT/UNIT as smaller “#” suffix |
| `TODO-046` | **Done** | Appreciation caption — lime when &gt; 6%/yr (amber &lt; 3% kept) |
| `TODO-047` | **Open** | Nearby chips — click opens source URL in browser (not property page) |
| `TODO-048` | **Open** | Playground library icon — investigate low hit rate; widen radius and/or match criteria |

Full write-ups: [`docs/TODO.md`](docs/TODO.md).  
**Before implementing overlays / area signals:** read [`docs/RESEARCH.md`](docs/RESEARCH.md) — do not re-research from scratch.

## Product decisions (locked)

1. **Ingest:** Zillow URL → store link + resolved address. No full MLS API. Listing HTML via `curl_cffi` (Chrome impersonation) for photos/details — Zillow blocks plain httpx.
2. **Street View:** Free Google `svembed` only; shown **below the map** on the Map tab in a dense collapsible expansion (open by default). Panel is 16:9 with `max-height: min(42vh, 480px)` (no min-height empty shell). Action row: Open in Google Maps / Open Street View / **Open in Google Earth** (`earth.google.com/web/@lat,lng,…` new tab) when pinned. No Maps Embed API keys for SV.
2b. **Map chrome:** Dark CARTO basemap (`apply_dark_basemap`); compact **neo text toggles** for overlays above the map (short labels; `.hb-map-layer-btn`, cyan glow only when on); single status line; Pin tools expansion below the map (collapsed). Fullscreen via `leaflet.fullscreen` (CDN + `fullscreenControl` options from `leaflet_map_kwargs()`), control near zoom; Escape / browser exit restores the in-tab map. No always-on Census tip — message only when Income toggle fails / key missing.
3. **Geocode:** Strip `UNIT`/`APT`/`#`/Suite; fallback query chain. Nominatim User-Agent: `Homebuy/0.1 (local research app)`.
4. **Optional env:** `GOOGLE_MAPS_API_KEY` (preferred geocoding + library grocery/shelter via Places Nearby Search when set); `CENSUS_API_KEY` (Map ACS tract choropleths + Financials ACS county tax estimate + buy-vs-rent rent-growth CAGR — required for those); `SOCRATA_APP_TOKEN` (optional, crime / Form 477 rate limits); `FCC_BDC_USERNAME` + `FCC_BDC_HASH` (or `FCC_BDC_HASH_VALUE`) — enables library missing-broadband chip (see §8b); `GEMINI_API_KEY` (Neighborhood AI + Financials commentary); `GEMINI_MODEL` / `GEMINI_FINANCIAL_MODEL` (see §6 / §6b). Assigned-school quality (see §6e) needs **no key** — it's free CA School Dashboard data + a Niche deep link.
5. **Theme accents:** Cyan `#00E5FF`, Magenta `#FF2BD6`, Lime `#B8FF3C`, Amber `#FFC107`.
5b. **Visual foundation:** Neon glow is a priority ladder (L1 focus/CTA/tabs/brand; L2 **library card** hover only; L3 chips quiet). **Akira Expanded** = street address + brand; **Creato Display** = body/UI/price (SIL OFL; Akira personal-use/demo — gitignored). Drop `.otf` files in `app/static/fonts/`. Library: stretch-to-match thumb, street hero, quieter price, Creato page chrome; responsive address clamp + stack under ~800px. **All buttons** use dark neumorphism (Quasar primary/secondary/outline remapped to soft neo faces — no cyan fill or cyan outline rings); optional `.hb-btn-cta` for brighter label + cyan hover. Map layers / tabs same language. Photos lightbox: `.hb-lightbox*`. Financials form: primary 2-col `.hb-financial-form` (deal + rent) with collapsed Loan / Ownership / Advanced expansions; `.hb-field-help` / `.hb-field-revert`. **Property header photo:** `PROPERTY_HEADER_PHOTO_MODE` in `pages.py` — `"bleed"` (default, full-bleed + scrim) or `"beside"` (library-card thumb). Rule: `.cursor/rules/homebuy-visual.mdc`.
5c. **Gemini in-tab:** Neighborhood overview / things-to-do and Financials commentary have Ask / Regenerate inside their tabs (in-place refresh); header Gemini insights may still exist as a bulk shortcut.
5d. **Library filter/nav:** Filter fields apply on Enter and after short debounce; open expansion button is **Apply**; collapsed label shows `Filter · N active`. Brand wordmark navigates to `/`; property page uses Home icon + brand (no redundant Back).
6. **Neighborhood reviews:** Prefer **Zillow listing neighborhood** name; fallback Nominatim/Google; manual override. **Gemini** (`GEMINI_API_KEY`, model `GEMINI_MODEL` default `gemini-3.1-flash-lite`) writes a cached overview paragraph (`neighborhood_gemini` / `neighborhood_gemini_for`, key `overview_v3|address|name|city|state`) and a separate cached things-to-do list (`neighborhood_things_to_do` / `neighborhood_things_to_do_for`, key `things_v3|address|name|city|state`). Prompts include the property’s **exact street address** plus neighborhood/city/state so answers can use block-level / walkshed context. Regenerating one does not wipe the other; both clear when the neighborhood override changes. Deep links only for Reddit/City-Data/Niche (no scrape); Niche uses a `/places-to-live/n/{hood}-{city}-{state}/` place URL when possible, else search. Notes in `neighborhood_notes`.
6b. **Financials Gemini:** Reads **Zillow URLs** via Gemini **URL context** (+ Google Search). Model: `GEMINI_FINANCIAL_MODEL` → else `GEMINI_MODEL` → else `gemini-2.5-flash-lite`. Prompt includes subject `zillow_url` + other library Zillow links only — no calculator/library field dump. Opinion sections: Why / Market & location / Buy vs rent. Cache `fin_v4|<url-hash>`. Ask uses warm cache; Regenerate forces refresh. Generate via Ask/Regenerate on Financials (or header insights).
6b2. **Financials deal inputs:** Primary surface = **Your deal** (offer + down $) and **Buy vs rent** (comparable rent + rent control). **Loan**, **Ownership costs**, and **Advanced buy vs rent** are collapsed expansions. Each field has low-opacity `?` help (how defaults/autofills work) and a restart **revert** control (`revert_financial_field`). Amber warning when down &lt; 20% (PMI may apply) + muted `≈ N%` caption. Enter in any field recalculates. Down $ is sticky if list/offer change.
6c. **Financials autofill:** on add / **Refresh listing details** / post-geocode re-sync, `_sync_financial_from_listing` overwrites `list_price`, `monthly_hoa`, `annual_property_tax`, `annual_insurance` from the Zillow listing — **down payment / term / closing are always preserved**. Interest rate is filled from Freddie Mac PMMS (TODO-012) unless `interest_rate_source` is `Manual`. Tax resolves Zillow annual tax → Zillow assessed value × rate → ACS county effective rate (`B25103`/`B25077`, needs `CENSUS_API_KEY`) × assessed-or-list-price basis; insurance scrapes Zillow’s modeled homeowners estimate (`annualHomeownersInsurance` and alternate/monthly keys, deep-walk + regex over `__NEXT_DATA__` / `gdpClientCache`) → state avg-premium table (`app/data/home_insurance_rates.json`) scaled to list price when the listing omits insurance (common on Showcase HTML). **Maintenance / month** autofills via `resolve_monthly_maintenance` (`app/core/home_maintenance.py`): age-banded % of effective price averaged with age `$/sqft × state index`, blended **60% reserve / 40% Angi** national maint+emergency ($1750+$978), then ÷12; CA index **1.15** in `app/data/home_maintenance_state_index.json` (index applies to $/sqft + observed legs, not as a second multiplier on % of price). Caption `maintenance_source` (e.g. `Estimated: age blend · CA×1.15`); edit → `Manual` (refresh preserves Manual). **Utilities / month** autofills via `resolve_monthly_utilities` (`app/core/utilities.py` + `app/data/utility_providers.json`): provider from city/ZIP (LADWP vs SCE electric + SoCalGas in LA-area; else Default) × sqft × age efficiency + water/trash; caption `utilities_source`; edit → `Manual`; never fails add-home. Also backfilled on Financials tab open via `ensure_financial` for homes synced before these features. Unresolved values fall back to `0` (no fake $500k/$6k/$1.8k placeholders); HOA explicit `$0` overwrites but an absent HOA field keeps the previous value. Each resolution records a short source string (`property_tax_source` / `insurance_source` / `interest_rate_source` / `maintenance_source` / `utilities_source`) shown as a caption under the inputs.
6c2. **Mortgage rates:** `app/core/mortgage_rates.py` pulls weekly PMMS 15-yr / 30-yr averages (Freddie Mac page, FRED fallback), caches ~6h under `data/cache/mortgage_rates/`. Maps term years to the closer of 15 vs 30. Applied on sync/`ensure_financial`; Term change in UI refreshes rate when not Manual; editing rate sets Manual. No API key.
6d. **Financials buy vs rent chart:** Shared **housing budget** (default **$13,000**/mo): both buy and rent invest `max(0, budget − housing_cost)`. Buyer cost = PITI + maintenance + **utilities** − tax shield/12; shield = `marginal_tax% × (year’s mortgage interest + min(property tax, SALT cap))` (defaults **41%** / **$10k** SALT, CA MFJ-style). Buy NW each year = `home×(1−sell%) − loan − CG tax + buyer surplus portfolio`; CG tax on `max(0, amount_realized − basis − exclusion)` at **cg_tax%** (defaults **24%** / exclusion **$500k** MFJ). Rent NW = portfolio seeded with cash-to-close + renter surplus. Other inputs: rent / rent control / appreciation / invest return / sell cost; maintenance + utilities under Ownership. Hero **Monthly payment** = PITI + maint + utils (`monthly_owner_total`); PITI-only math unchanged. Rent prefilled from Zillow `rentZestimate` (else **$5300** / `Default`). Rent growth: control → **2%/yr**; else ACS B25064 CAGR or **3%**. Persist `monthly_budget`, `marginal_tax_pct`, `cg_tax_pct`, `cg_exclusion`, `salt_cap`, plus prior buy-vs-rent fields. Simplified taxes (not a full return). Charts = monthly mix pie + this dual-line. Gemini fingerprint unchanged.
6e. **Assigned schools (Neighborhood tab):** Separate from the Map **Schools** overlay (NCES points, unchanged). `app/core/school_zones.py` resolves the **Elementary / Middle / High** schools a pin is zoned for via **LAUSD attendance-boundary point-in-polygon** — queries `LAUSD_Schools` ArcGIS MapServer attendance layers **4/5/6** (ES/MS/HS) at the pin, then resolves each zone's school **name** from layer-**0** school points within 3 mi whose location falls inside the returned zone polygon (`point_in_polygon`; prefers exact `MAP_TYPE` match, ties broken by distance to the pin). `resolve_assigned(lat, lng)` returns `status` `ok` / `outside` / `gap` (inside the rough LAUSD bbox but no attendance hit — rare boundary gap) / `no_pin` / `error`, cached ~7d under `data/cache/school_zones/`. **v1 geography: LAUSD only** — other districts show "not available for this district yet." `app/core/school_quality.py` enriches each resolved school for **free, no API key**: a **CA School Dashboard** performance-level color (Blue/Green/Yellow/Orange/Red) looked up by 14-digit CDS code from the free CDE Academic Indicator downloadable data (ELA, All Students, school-level rows; TXT downloaded once from `www3.cde.ca.gov/researchfiles/cadashboard/eladownload2025.txt` and cached as a slim `cds → {color, status, year}` map ~30d under `data/cache/ca_dashboard/`, same one-time-ingest pattern as Redfin), plus a **Niche** parent-review search deep link and a **CA Dashboard** report-page deep link. `enrich_assigned`/`enrich_school` always run (no key gate); if the CDE download/lookup fails or misses, cards still show the Niche + Dashboard links with no color badge. UI: three cards (Elementary cyan / Middle magenta / High lime accent) on **Neighborhood**, placed after the name/override row and before the Gemini overview; resolved off the event loop via `resolve_assigned_schools_job` (`ui_jobs.py`) with instant "Loading…" placeholders. The Map tab's **Nearby schools** panel (distance list) was removed — the Schools layer toggle, NCES markers, and legend on Map are unchanged.
7. **Map overlays:** Exclusive layer toggles only (turning one on clears the others; no Neighborhood chips). FEMA NFHL WMS flood; **Zoning** GeoJSON near pin for **City of Los Angeles** (ZIMAS MapServer **1102** citywide Zoning — not Chapter 1A `1101` pockets; ACS-scale ~0.04° bbox + ArcGIS pagination; generalized + slim props + merge by zone_code for NiceGUI ~1 MB WS; status shows zones/parcels + `~N mi radius`), **Santa Monica** (SCAG parcel zoning; city AGOL layer needs State Plane), and **unincorporated LA County** (DRP), with SCAG fallback for other LA County cities when DRP is empty; ACS tract choropleths for **median income** (`B19013`), **median home value** (`B25077`), **median age** (`B01002`), **avg kids under 18 per household** (`B09001`/`B25003`), **% owner-occupied** (`B25003`), **median year built** (`B25035`), **median gross rent** (`B25064`), and **% bachelor's+** (`B15003`) — ACS needs `CENSUS_API_KEY`; crime near pin for **all of LA County** (merges LAPD Socrata + Santa Monica CKAN; densest in those PDs) and Seattle — rendered as a **hex density choropleth** (incident counts per cell), not individual report dots; **Schools** — NCES EDGE public school points within ~4 mi (`schools_nces.py`, bbox query, no GreatSchools; no Nearby-schools list on Map — see §6e for the Neighborhood-tab assigned-schools cards); **Wildfire** — USFS WHP 2023 WMS; **AQI** — Open-Meteo US AQI hex grid (no key); **Sale price** — Redfin Data Center ZIP median → TIGER ZCTA join (`redfin_sales.py`, slim cached ingest). Also resolves from pin lat/lng when city is empty. Cache under `data/cache/`.
8. **Library page:** list layout, not a grid. Cards (`.hb-library-card`, stretch thumb) are whole-card-clickable; **Open on Zillow** / **Delete…** live in a ⋮ overflow menu (stopPropagation). Delete still confirms. Large Akira street + quieter Creato price; primary chips for beds/baths/sqft/`$`-sqft; quieter chips for type/year; HOA ≥ $400/mo uses amber `.hb-meta-chip--hoa-high`. Quiet financial caption (`PITI $…/mo`) when `FinancialAssumptions` exist (`library_export.snapshot_from_property` + `finance.summarize`); appreciation as `Growth N%/yr` beside it (amber `.hb-appr-low` when &lt; 3%; lime `.hb-appr-high` when &gt; 6%; neutral 3–6%). Street line ~10% smaller Akira; APT/UNIT/SUITE/# display as smaller `#…` suffix (`.hb-library-unit`) — stored address unchanged. Notes teaser (truncated) when set. Sort select: Newest / Price ↑ / Price ↓. Filter expansion shows “N active” when filters set. Compact Add (hide helper line) when the DB already has homes. **Export** toolbar menu → CSV/JSON of full library + key financial fields. No side-by-side Compare (removed TODO-027). **Thumbnails:** auto-pick prefers exterior on add; `thumbnail_locked` + Photos pin (“Use as library thumbnail”). Photos tab is view/pin only (no re-import / upload / auto-pick controls).
8a. **Library nearby icons (not Map overlays):** `app/core/nearby_signals.py` queries OSM Overpass around the pin for all five signals; when `GOOGLE_MAPS_API_KEY` is set, Places Nearby Search refines grocery (≤0.5 mi) and shelter/recovery (≤0.5 mi), merging with OSM (nearer wins — Places empty never wipes OSM). Thresholds: highway ≤800 ft (`motorway`/`motorway_link` only, nearest way vertex); transit ≤0.5 mi (subway/light rail/tram, not buses); playground ≤0.75 mi (`leisure=playground` nodes/ways/relations + `leisure=park`+`playground=yes`); grocery ≤0.5 mi; shelter ≤0.5 mi (`amenity=social_facility` with `social_facility` in shelter/drug_rehabilitation/transitional or `social_facility:for` containing homeless; `amenity=shelter` + `shelter_type=homeless` or `homeless=yes` — not bus-stop weather shelters). Way polygons use `out center geom tags` + geometry fallback so playground/shelter buildings are not dropped. Places shelter uses separate keyword searches (`homeless shelter`, `transitional housing`, `drug rehabilitation`) with name/type filtering. Results persist as JSON on `Property` (`nearby_signals`, `nearby_signals_at`); raw Overpass/Places responses cached ~7d under `data/cache/nearby/` (`overpass_v2_*` keys after TODO-036). Compute on add + post-geocode; library load best-effort refreshes up to **3** stale/missing pins (> ~30 days). UI: soft neo chips bottom-right on the library card (not over the photo) in fixed order; highway/shelter = magenta risk, transit/playground/grocery = lime amenity; hover shows distance + nearest name; chip click does not open the card. Add-home never fails on lookup errors. No manual refresh, Map markers, or library filters in v1.
8b. **Library listing risk chips (TODO-039 + TODO-042):** scrape Zillow cooling into `Property.cooling` + nullable `has_central_ac` on add/refresh (`zillow_listing.py`). `app/core/listing_signals.py` exposes `listing_risk_chips(prop)` — magenta `ac_unit` when central AC is clearly absent; magenta `wifi_off` when FCC reports **no fixed terrestrial broadband** (`app/core/fcc_broadband.py`: requires `FCC_BDC_USERNAME` + `FCC_BDC_HASH`; geo.fcc.gov block + Living Atlas BDC UniqueProviders*; DSL/cable alone does **not** flag; no credentials → unknown / no chip). Persist `broadband_status` / `broadband_at`; compute on add/post-geocode. Rendered in `.hb-nearby-icons` on library cards + property header via `_extra_signal_chips`.
8c. **Library high-permit chip (TODO-043):** `app/core/permits_nearby.py` queries city Socrata SODA feeds with `within_circle` (~0.25 mi / 402 m) for **Los Angeles** (`pi9x-tg5x` / `geolocation`), **Seattle** (`76t5-zqzr` / `location1`), and **Austin** (`3syk-w9eu` / `location`). Counts structural / electrical / demolition-ish permits issued in the last **24 months** (excludes withdrawn/canceled); **high activity ≥ 8**. Persist JSON on `Property` (`permits_activity`, `permits_activity_at`); compute on add + post-geocode best-effort; raw responses cached ~7d under `data/cache/permits/`; optional `SOCRATA_APP_TOKEN`. Outside supported cities → no chip. Amber `.hb-nearby-chip--amber` `construction` chip via `chip_spec_for` → `_extra_signal_chips` on library + header. Stale refresh on library paint: `refresh_stale_permits_activity_job`.

## Working agreements for agents

- **After completing any user-facing feature or meaningful fix, update both `AGENTS.md` and `README.md`** in the same turn (status, how-to-use, decisions). Do not leave continuity docs stale.
- Prefer **parallel Task subagents** for independent features; declare file ownership to avoid merge fights (`models.py` / `property_service.py` / `pages.py` are hotspots).
- After UI/backend changes, **restart** `python -m app.main` (reload is off).
- Long UI work (Zillow scrape, geocode, nearby, Gemini, map overlay fetches) must use `await run.io_bound(...)` with workers in `app/core/ui_jobs.py` (own `get_session()`; never pass ORM/UI objects into threads) — otherwise NiceGUI shows “Connection lost”.
- Don’t commit unless the user asks.
- Don’t scrape in ways that need exploit kits; prefer official APIs where ToS matters (esp. Reddit).
- Keep modules thin; put shared logic in `app/core/`.

## Quick verify checklist

1. Library loads dark theme at http://127.0.0.1:8080 as a list of clickable home cards (stretch thumb, Akira street with compact `#unit` when present, quieter price, meta chips, quiet PITI + Growth captions when financials exist — amber &lt;3% / lime &gt;6%, nearby proximity icons + no-central-AC risk chip when applicable at card bottom-right, ⋮ menu); Creato page chrome; Sort + collapsed Filter with active count; Export CSV/JSON; muted homes count next to the heading
2. Paste a `/homedetails/..._zpid/` URL → Add home → photos + address + beds/price/sqft/HOA/year/type/cooling appear; card click opens the property; menu Zillow/Delete don't navigate the card; delete confirms; Photos pin sets library thumb  
3. Map pins (even with `UNIT` in the slug)  
4. Map tab: dark CARTO basemap; fullscreen control near zoom; flood/zoning/wildfire/AQI/schools/sale-price/income/crime toggles (Schools → NCES markers + legend only, no Nearby-schools panel); Street View expansion below map (free svembed, dense chrome, Maps/SV/Earth open links when pinned); no always-on Census tip until Income is toggled without a key  
5. Financials: primary **Your deal** + rent/**Rent control**; **Loan** / **Ownership** (tax/insurance/HOA/maint/**utilities**) / **Advanced** behind expansions; `?` help + per-field revert; offer + down in dollars (amber warn if &lt;20%); Enter recalculates; add/refresh → list/HOA/tax/insurance/rent/appreciation/rent-growth/maint/utilities match listing or show ACS/state/FHFA/Zillow/age-blend/provider/Default captions; interest rate from Freddie Mac PMMS by term (Manual if edited); **Rent control** → 2%/yr; unchecked → ACS county rent CAGR or 3% default; hero monthly = PITI + maint + utils; charts = monthly mix pie + **Buy vs rent + invest (net worth)**; Gemini Ask / Regenerate when `GEMINI_API_KEY` is set
6. Neighborhood tab resolves a name, deep-link buttons open Reddit/City-Data/Niche/Google; for an **LAUSD-pinned** home, **Assigned schools** shows three Elementary/Middle/High cards (names, a free CA Dashboard color badge when the CDS lookup hits, and Dashboard/Niche link buttons — no keys needed); Gemini overview + things-to-do buttons work when `GEMINI_API_KEY` is set  
7. Property header: muted **Edit listing details** below Refresh/Gemini; nearby proximity chips bottom-right of `.hb-property-hero` when cached signals exist  
8. `.\.venv\Scripts\pytest.exe -q` passes  

## Related docs

- `README.md` — user-facing run instructions  
- `.env.example` — optional keys  
- This file (`AGENTS.md`) — continuity for AI agents  
- `docs/RESEARCH.md` — map overlays + neighborhood research notes  
- `docs/TODO.md` — product backlog (listing scrape, area signals, Gemini sections)  
- `docs/BUGS.md` — deferred bugs / verify-later items 
