# Homebuy — Agent Continuity Guide

> Read this first when starting a new agent session on this project.
> Last updated: 2026-07-18 (Cleanup sweep #2 — docs sync, Gemini cache dedupe, financial sync trim)

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
| Geocode (unit stripping + fallbacks) | `app/core/geocode.py` |
| Photo import | `app/core/zillow_photos.py` |
| Listing fields extract | `app/core/zillow_listing.py` |
| Neighborhood + Gemini overview / things-to-do | `app/core/neighborhood.py`, `app/core/gemini_neighborhood.py` |
| Financials Gemini commentary | `app/core/gemini_financial.py` |
| Mortgage rates (Freddie Mac PMMS) | `app/core/mortgage_rates.py` |
| Library thumbnail pick | `app/core/thumbnail.py` |
| Mortgage math + buy vs rent projection | `app/core/finance.py` |
| FHFA ZIP HPI (~10y CAGR, no API key) | `app/core/fhfa_hpi.py` |
| Map overlays | `app/core/{census_acs,fema_flood,crime_socrata,crime_density,zoning_gis,overlay_cache}.py` |
| Dark basemap | `app/core/map_basemap.py` (CARTO `dark_all` after `ui.leaflet`) |
| Modules | `app/modules/{gallery,map_view,neighborhood_reviews,financial}.py` (+ `street_view.py` helpers, no tab) |
| Env template | `.env.example` |

### Data model (high level)

**Property:** `address`, `zillow_url`, `list_price`, `beds`, `baths`, `sqft`, `hoa_fee`, `year_built`, `home_type`, `city`, `state`, `zip_code`, `latitude`, `longitude`, `thumbnail_photo_id`, `thumbnail_locked`, `notes`, `neighborhood_name`, `neighborhood_source`, `neighborhood_override`, `neighborhood_notes`, `neighborhood_gemini`, `neighborhood_gemini_for`, `neighborhood_things_to_do`, `neighborhood_things_to_do_for`, `financial_gemini`, `financial_gemini_for`

**Photo:** `path`, `source_url`, `caption`, `sort_order`

**FinancialAssumptions:** `list_price`, `offer_price`, loan/ownership fields (math uses **offer** if set, else list). Legacy `purchase_price` kept in sync. `property_tax_source` / `insurance_source` / `interest_rate_source` record how tax / insurance / rate were resolved (e.g. `Zillow`, `Freddie Mac PMMS 30-yr FRM · …`) and are shown as UI captions. Buy-vs-rent: `monthly_rent`, `rent_source`, `rent_control`, `rent_growth_pct`, `rent_growth_source`, `appreciation_pct`, `appreciation_source`, `appreciation_fhfa_pct`, `appreciation_zillow_pct` (FHFA/Zillow components kept for chart captions even when appreciation is manually overridden).

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
- [x] Map overlays: FEMA flood WMS + Zoning (LA City/SM/County) + full ACS tract set (income, home value, median age, avg kids, % owner-occupied, year built, gross rent, % bachelor's+) + LA County crime (LAPD Socrata + Santa Monica CKAN) + Seattle hex density choropleth
- [x] Street View folded into Map tab (map on top, free svembed below; no standalone SV tab)
- [x] Map tab Direction 1 polish: CARTO dark basemap, compact layer bar, taller map, quieter status, Pin tools + collapsible Street View below map
- [x] Map fullscreen control (leaflet.fullscreen near zoom; survives redraw)
- [x] Richer Zillow listing scrape: beds, price, sqft, HOA, year built, home type (library + header + edit)
- [x] Library visual refresh + iteration 2: list cards (~180×135 thumb), neon price, chips + amber HOA ≥$400, notes teaser, ⋮ menu (Zillow/Delete), sort + filter active count, compact Add when nonempty; lockable library thumb from Photos + stronger exterior auto-pick
- [x] Visual foundation (2026-07-18): hierarchy-through-emission; Creato + Akira self-host; library street hero + stretch thumb; page chrome (title/Add/Filter/empty) matched to cards
- [x] Property tab chrome (2026-07-18): property header (Akira street + chips), Photos/Map/Neighborhood/Financials titles/hints/empty states + dense controls; Leaflet/Plotly/svembed unchanged
- [x] Property header library photo (2026-07-18): full-bleed + scrim by default (`PROPERTY_HEADER_PHOTO_MODE = "bleed"`); flip to `"beside"` for card-style thumb
- [x] Dark neumorphism on buttons + tabs (2026-07-18): extruded/inset soft faces; cyan reserved for primary CTA + active tab
- [x] Map overlay neo toggles (2026-07-18): checkbox row → label-only neo buttons with emissive glow when on
- [x] Audit polish batch (2026-07-18): Financials 2×2 form grid; library-only card hover; short Map overlay labels + toggle `--on` fix; Quasar greys → `hb-*`; neo Photos lightbox + actions above grid; Filter Enter/debounce + Apply; clickable brand / no redundant Back; library responsive clamp/stack; in-tab Gemini Ask/Regenerate (Financials + Neighborhood)
- [x] TODO-006 codebase cleanup (2026-07-18): dead helpers removed, single Zillow HTML fetch on add, batched photo import, fewer redundant DB loads, overlay cache prune on miss, lazy Plotly import — features unchanged
- [x] TODO-011 Financials autofill (2026-07-18): list price/HOA/tax/insurance filled from the Zillow listing on add/refresh, with a tax chain (Zillow → assessed×rate → ACS county rate) and a state avg-premium insurance fallback; source captions shown under the Ownership inputs; down/term/closing never overwritten
- [x] TODO-012 Mortgage rate autofill (2026-07-18): Interest rate filled from Freddie Mac PMMS 15/30 averages by loan term (closer product); caption under rate; Manual override when edited; Term change refreshes matching average
- [x] Financials deal UX (2026-07-18): Your deal = offer + down in dollars with &lt;20% amber PMI warning; Assumptions quieter below
- [x] Financials buy vs rent + invest chart (2026-07-18): fourth Plotly dual-line (buy net worth vs rent + invest); FHFA ZIP5 ~10y CAGR + Zillow decade % blended (default 3% if both missing); rentZestimate prefill; fixed 6% sell cost / 10% invest return in v1; loan terms never overwritten
- [x] Financials rent growth + rent control (2026-07-18): **Rent control** checkbox beside comparable rent → **2%/yr**; unchecked → ACS county **B25064** ~5y CAGR via `county_median_rent_cagr` (needs `CENSUS_API_KEY`, county from pin); **3%** / `Default` on miss; rent rises in projection (`rent_growth_pct`); owner **PITI flat**; captions under rent + chart; Manual override clears control
- [x] FHFA ZIP5 parser header fix (2026-07-18): scans past workbook title/notes for ZIP + year + HPI-level headers; exact `HPI` is preferred over Annual Change (%); regression test covers the real workbook layout
- [x] Cleanup sweep #2 (2026-07-18): Gemini Ask uses warm cache without re-calling API; deduped financial sync on add/refresh; docs aligned to overlays/Census/Gemini env vars

## In progress / next (as of last session)

| ID | Status | Notes |
|----|--------|-------|
| `TODO-002` | **Partial** | Area signals still open: AQI, fire risk, Redfin sale-price choropleth; more cities’ zoning beyond LA/SM/County |

Full write-ups: [`docs/TODO.md`](docs/TODO.md).  
**Before implementing overlays / area signals:** read [`docs/RESEARCH.md`](docs/RESEARCH.md) — do not re-research from scratch.

## Product decisions (locked)

1. **Ingest:** Zillow URL → store link + resolved address. No full MLS API. Listing HTML via `curl_cffi` (Chrome impersonation) for photos/details — Zillow blocks plain httpx.
2. **Street View:** Free Google `svembed` only; shown **below the map** on the Map tab in a collapsible expansion (open by default, shorter panel). No Maps Embed API keys for SV.
2b. **Map chrome:** Dark CARTO basemap (`apply_dark_basemap`); compact **neo text toggles** for overlays above the map (short labels; `.hb-map-layer-btn`, cyan glow only when on); single status line; Pin tools expansion below the map (collapsed). Fullscreen via `leaflet.fullscreen` (CDN + `fullscreenControl` options from `leaflet_map_kwargs()`), control near zoom; Escape / browser exit restores the in-tab map. No always-on Census tip — message only when Income toggle fails / key missing.
3. **Geocode:** Strip `UNIT`/`APT`/`#`/Suite; fallback query chain. Nominatim User-Agent: `Homebuy/0.1 (local research app)`.
4. **Optional env:** `GOOGLE_MAPS_API_KEY` (preferred geocoding); `CENSUS_API_KEY` (Map ACS tract choropleths + Financials ACS county tax estimate + buy-vs-rent rent-growth CAGR — required for those); `SOCRATA_APP_TOKEN` (optional, crime rate limits); `GEMINI_API_KEY` (Neighborhood AI + Financials commentary); `GEMINI_MODEL` / `GEMINI_FINANCIAL_MODEL` (see §6 / §6b).
5. **Theme accents:** Cyan `#00E5FF`, Magenta `#FF2BD6`, Lime `#B8FF3C`, Amber `#FFC107`.
5b. **Visual foundation:** Neon glow is a priority ladder (L1 focus/CTA/tabs/brand; L2 **library card** hover only; L3 chips quiet). **Akira Expanded** = street address + brand; **Creato Display** = body/UI/price (SIL OFL; Akira personal-use/demo — gitignored). Drop `.otf` files in `app/static/fonts/`. Library: stretch-to-match thumb, street hero, quieter price, Creato page chrome; responsive address clamp + stack under ~800px. **All buttons** use dark neumorphism (Quasar primary/secondary/outline remapped to soft neo faces — no cyan fill or cyan outline rings); optional `.hb-btn-cta` for brighter label + cyan hover. Map layers / tabs same language. Photos lightbox: `.hb-lightbox*`. Financials form: 2×2 `.hb-financial-form`. **Property header photo:** `PROPERTY_HEADER_PHOTO_MODE` in `pages.py` — `"bleed"` (default, full-bleed + scrim) or `"beside"` (library-card thumb). Rule: `.cursor/rules/homebuy-visual.mdc`.
5c. **Gemini in-tab:** Neighborhood overview / things-to-do and Financials commentary have Ask / Regenerate inside their tabs (in-place refresh); header Gemini insights may still exist as a bulk shortcut.
5d. **Library filter/nav:** Filter fields apply on Enter and after short debounce; open expansion button is **Apply**; collapsed label shows `Filter · N active`. Brand wordmark navigates to `/`; property page uses Home icon + brand (no redundant Back).
6. **Neighborhood reviews:** Prefer **Zillow listing neighborhood** name; fallback Nominatim/Google; manual override. **Gemini** (`GEMINI_API_KEY`, model `GEMINI_MODEL` default `gemini-3.1-flash-lite`) writes a cached overview paragraph (`neighborhood_gemini` / `neighborhood_gemini_for`) and a separate cached things-to-do list (`neighborhood_things_to_do` / `neighborhood_things_to_do_for`, key prefix `things_v2|`). Regenerating one does not wipe the other; both clear when the neighborhood override changes. Deep links only for Reddit/City-Data/Niche (no scrape); Niche uses a `/places-to-live/n/{hood}-{city}-{state}/` place URL when possible, else search. Notes in `neighborhood_notes`.
6b. **Financials Gemini:** Reads **Zillow URLs** via Gemini **URL context** (+ Google Search). Model: `GEMINI_FINANCIAL_MODEL` → else `GEMINI_MODEL` → else `gemini-2.5-flash-lite`. Prompt includes subject `zillow_url` + other library Zillow links only — no calculator/library field dump. Opinion sections: Why / Market & location / Buy vs rent. Cache `fin_v4|<url-hash>`. Ask uses warm cache; Regenerate forces refresh. Generate via Ask/Regenerate on Financials (or header insights).
6b2. **Financials deal inputs:** Primary **Your deal** column = Offer price + Down payment in **dollars** (stored as `down_payment_pct`; UI converts via effective price). Amber warning icon when down &lt; 20% (PMI may apply) + muted `≈ N%` caption. Quieter **Loan** + **Ownership costs** columns beside it (list/rate/term/closing; tax/insurance/HOA). Enter in any field recalculates. Down $ is sticky if list/offer change.
6c. **Financials autofill:** on add / **Refresh listing details** / post-geocode re-sync, `_sync_financial_from_listing` overwrites `list_price`, `monthly_hoa`, `annual_property_tax`, `annual_insurance` from the Zillow listing — **down payment / term / closing are always preserved**. Interest rate is filled from Freddie Mac PMMS (TODO-012) unless `interest_rate_source` is `Manual`. Tax resolves Zillow annual tax → Zillow assessed value × rate → ACS county effective rate (`B25103`/`B25077`, needs `CENSUS_API_KEY`) × assessed-or-list-price basis; insurance resolves Zillow annual insurance → state avg-premium table (`app/data/home_insurance_rates.json`) scaled to list price. Unresolved values fall back to `0` (no fake $500k/$6k/$1.8k placeholders); HOA explicit `$0` overwrites but an absent HOA field keeps the previous value. Each resolution records a short source string (`property_tax_source` / `insurance_source` / `interest_rate_source`) shown as a caption under the inputs.
6c2. **Mortgage rates:** `app/core/mortgage_rates.py` pulls weekly PMMS 15-yr / 30-yr averages (Freddie Mac page, FRED fallback), caches ~6h under `data/cache/mortgage_rates/`. Maps term years to the closer of 15 vs 30. Applied on sync/`ensure_financial`; Term change in UI refreshes rate when not Manual; editing rate sets Manual. No API key.
6d. **Financials buy vs rent chart:** **Buy vs rent** inputs = comparable monthly rent + **Rent control** checkbox + appreciation %/yr (source captions like tax/insurance). Rent prefilled from Zillow `rentZestimate` on add/refresh unless `rent_source` is `Manual`. **Rent growth:** checkbox on → fixed **2%/yr** (`rent_control=True`, source `Rent control 2%`); off → ACS county median gross rent **B25064** ~5y CAGR (`county_median_rent_cagr` in `app/core/census_acs.py`, county from pin lat/lng, needs `CENSUS_API_KEY`); ACS miss / no key → **3%** / `Default`. Persist `rent_control`, `rent_growth_pct`, `rent_growth_source`; editing growth % sets `Manual` and unchecks control. Quiet caption under rent (e.g. `Growth 2.00%/yr · Rent control 2%` or `Growth 3.41%/yr · ACS county ~5y CAGR`). Appreciation = mean of available FHFA ZIP5 ~10y CAGR (`app/core/fhfa_hpi.py`, public XLSX, cached ~30d under `data/cache/fhfa/`, **no API key**) and Zillow listing decade %; default **3%** if both missing; user override sets `appreciation_source = Manual` (component columns kept for caption). Fourth Plotly chart compares **buy net worth** (home value − loan balance − **6%** sell cost each year) vs **rent + invest** (cash-to-close + monthly `max(0, PITI − rent(t))` compounded at **10%/yr**, where `rent(t) = rent₀ × (1 + rent_growth_pct/100)^t`); **owner PITI stays flat** for the horizon. Fixed 6%/10% in v1 (captioned, not editable). Recalculate redraws from current fields; FHFA/Zillow/ACS rent-growth lookups on add/refresh (and cache miss), not every keystroke. Gemini fingerprint unchanged.
7. **Map overlays:** Exclusive layer toggles only (turning one on clears the others; no Neighborhood chips). FEMA NFHL WMS flood; **Zoning** GeoJSON near pin for **City of Los Angeles** (ZIMAS), **Santa Monica** (SCAG parcel zoning; city AGOL layer needs State Plane), and **unincorporated LA County** (DRP), with SCAG fallback for other LA County cities when DRP is empty; ACS tract choropleths for **median income** (`B19013`), **median home value** (`B25077`), **median age** (`B01002`), **avg kids under 18 per household** (`B09001`/`B25003`), **% owner-occupied** (`B25003`), **median year built** (`B25035`), **median gross rent** (`B25064`), and **% bachelor's+** (`B15003`) — ACS needs `CENSUS_API_KEY`; crime near pin for **all of LA County** (merges LAPD Socrata + Santa Monica CKAN; densest in those PDs) and Seattle — rendered as a **hex density choropleth** (incident counts per cell), not individual report dots. Also resolves from pin lat/lng when city is empty. Cache under `data/cache/`.
8. **Library page:** list layout, not a grid. Cards (`.hb-library-card`, stretch thumb) are whole-card-clickable; **Open on Zillow** / **Delete…** live in a ⋮ overflow menu (stopPropagation). Delete still confirms. Large Akira street + quieter Creato price; primary chips for beds/baths/sqft/`$`-sqft; quieter chips for type/year; HOA ≥ $400/mo uses amber `.hb-meta-chip--hoa-high`. Notes teaser (truncated) when set. Sort select: Newest / Price ↑ / Price ↓. Filter expansion shows “N active” when filters set. Compact Add (hide helper line) when the DB already has homes. **Thumbnails:** auto-pick prefers exterior on add; `thumbnail_locked` + Photos pin (“Use as library thumbnail”). Photos tab is view/pin only (no re-import / upload / auto-pick controls).

## Working agreements for agents

- **After completing any user-facing feature or meaningful fix, update both `AGENTS.md` and `README.md`** in the same turn (status, how-to-use, decisions). Do not leave continuity docs stale.
- Prefer **parallel Task subagents** for independent features; declare file ownership to avoid merge fights (`models.py` / `property_service.py` / `pages.py` are hotspots).
- After UI/backend changes, **restart** `python -m app.main` (reload is off).
- Don’t commit unless the user asks.
- Don’t scrape in ways that need exploit kits; prefer official APIs where ToS matters (esp. Reddit).
- Keep modules thin; put shared logic in `app/core/`.

## Quick verify checklist

1. Library loads dark theme at http://127.0.0.1:8080 as a list of clickable home cards (stretch thumb, Akira street, quieter price, meta chips, ⋮ menu); Creato page chrome; Sort + collapsed Filter with active count; muted homes count next to the heading  
2. Paste a `/homedetails/..._zpid/` URL → Add home → photos + address + beds/price/sqft/HOA/year/type appear; card click opens the property; menu Zillow/Delete don't navigate the card; delete confirms; Photos pin sets library thumb  
3. Map pins (even with `UNIT` in the slug)  
4. Map tab: dark CARTO basemap; fullscreen control near zoom; flood/income/crime toggles; Street View expansion below map (free svembed, open by default); no always-on Census tip until Income is toggled without a key  
5. Financials: **Your deal** / Loan / Ownership in three columns + **Buy vs rent** rent/**Rent control**/appreciation inputs; offer + down in dollars (amber warn if &lt;20%); Enter recalculates; add/refresh → list/HOA/tax/insurance/rent/appreciation/rent-growth match listing or show ACS/state/FHFA/Zillow/Default captions; interest rate from Freddie Mac PMMS by term (Manual if edited); **Rent control** → 2%/yr; unchecked → ACS county rent CAGR or 3% default; fourth chart **Buy vs rent + invest (net worth)** (cyan buy, magenta rent+invest, rising rent); Gemini Ask / Regenerate when `GEMINI_API_KEY` is set
6. Neighborhood tab resolves a name, deep-link buttons open Reddit/City-Data/Niche/Google; Gemini overview + things-to-do buttons work when `GEMINI_API_KEY` is set  
7. `.\.venv\Scripts\pytest.exe -q` passes  

## Related docs

- `README.md` — user-facing run instructions  
- `.env.example` — optional keys  
- This file (`AGENTS.md`) — continuity for AI agents  
- `docs/RESEARCH.md` — map overlays + neighborhood research notes  
- `docs/TODO.md` — product backlog (listing scrape, area signals, Gemini sections)  
- `docs/BUGS.md` — deferred bugs / verify-later items 
