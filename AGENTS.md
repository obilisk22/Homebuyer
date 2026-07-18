# Homebuy — Agent Continuity Guide

> Read this first when starting a new agent session on this project.
> Last updated: 2026-07-18 (Library home page visual refresh — list layout)

## What this is

**Homebuy** is a personal Python web app for researching homes linked from Zillow. Paste a Zillow listing URL → save the home → dive deeper than Zillow’s UI (photos, map, street view, financials). Built to be **module-extensible**.

| | |
|---|---|
| **Path** | `C:\Users\hheaf\Projects\homebuy` |
| **Stack** | Python 3.12, NiceGUI, SQLAlchemy + SQLite, Plotly, Leaflet, curl_cffi |
| **UI** | Dark cyberpunk theme (black/gray + cyan / magenta / lime neon) |
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
| Library thumbnail pick | `app/core/thumbnail.py` |
| Mortgage math | `app/core/finance.py` |
| Map overlays | `app/core/{census_acs,fema_flood,crime_socrata,overlay_cache}.py` |
| Dark basemap | `app/core/map_basemap.py` (CARTO `dark_all` after `ui.leaflet`) |
| Modules | `app/modules/{gallery,map_view,neighborhood_reviews,financial}.py` (+ `street_view.py` helpers, no tab) |
| Env template | `.env.example` |

### Data model (high level)

**Property:** `address`, `zillow_url`, `list_price`, `beds`, `baths`, `sqft`, `hoa_fee`, `year_built`, `home_type`, `city`, `state`, `zip_code`, `latitude`, `longitude`, `thumbnail_photo_id`, `notes`, `neighborhood_name`, `neighborhood_source`, `neighborhood_override`, `neighborhood_notes`, `neighborhood_gemini`, `neighborhood_gemini_for`, `neighborhood_things_to_do`, `neighborhood_things_to_do_for`

**Photo:** `path`, `source_url`, `caption`, `sort_order`

**FinancialAssumptions:** `list_price`, `offer_price`, loan/ownership fields (math uses **offer** if set, else list). Legacy `purchase_price` kept in sync.

SQLite migrations are lightweight `ALTER TABLE` helpers in `app/core/db.py` (`_migrate_sqlite`).

## What’s done

- [x] Project bootstrap, NiceGUI shell, module registry
- [x] Add home from Zillow URL only; import photos + listing details
- [x] Photos gallery + lightbox; exterior-ish library thumbnails
- [x] Gallery UX: denser larger tiles; no per-photo Remove (re-import replace only)
- [x] Map geocode (Nominatim default; optional Google key); unit/apt address fix
- [x] Street View free desktop 16:9 panel (no Cloud billing)
- [x] Financials: offer vs list, PITI + PMI, neon Plotly charts
- [x] Library search/filters (price, beds, city/address)
- [x] Cyberpunk dark theme
- [x] Add-home is Zillow URL only (address from listing/URL)
- [x] Initial Git commit + push to https://github.com/obilisk22/Homebuyer (`main`)
- [x] Neighborhood Reviews: Zillow neighborhood name + Gemini overview + things-to-do list + deep links/notes
- [x] Map overlays (slice): FEMA flood WMS + ACS median income choropleth + LA/Santa Monica/Seattle crime
- [x] Street View folded into Map tab (map on top, free svembed below; no standalone SV tab)
- [x] Map tab Direction 1 polish: CARTO dark basemap, compact layer bar, taller map, quieter status, Pin tools + collapsible Street View below map
- [x] Map fullscreen control (leaflet.fullscreen near zoom; survives redraw)
- [x] Richer Zillow listing scrape: beds, price, sqft, HOA, year built, home type (library + header + edit)
- [x] Library visual refresh: richer **list** cards (not a grid) — 160×120 thumb/placeholder, neon price, beds/baths/sqft/`$`-sqft chips + quieter type/year/HOA chips, whole-card click to property page, delete confirm dialog, collapsed Filter expansion, muted homes count

## In progress / next (as of last session)

| ID | Status | Notes |
|----|--------|-------|
| `map-overlays-research` | **Done** | See [`docs/RESEARCH.md`](docs/RESEARCH.md) |
| `neighborhood-reviews-research` | **Done** | See [`docs/RESEARCH.md`](docs/RESEARCH.md) |
| `neighborhood-reviews-impl` | **Done** | Module `neighborhood_reviews` (order 35); deep links only |
| `map-overlays-impl` | **Partial** | Flood + ACS income + LA/SM/Seattle crime; deferred Redfin / ACS value / AQI / fire |
| `TODO-001` | **Done** | Beds/price/sqft/HOA/year/home type from gdpClientCache + LD+JSON |
| `TODO-002` | **Partial** | Income + flood + LA/SM/Seattle crime on Map; still pending AQI, fire, avg home price |
| `TODO-003` | **Done** | `$/sqft` on library cards + property header |
| `TODO-004` | **Done** | Neighborhood tab: Gemini “cool things to do” (separate cache from overview) |
| `TODO-005` | Pending | Financials tab: Gemini breakdown + opinion |
| `TODO-006` | Pending | Clean up codebase |
| `TODO-007` | **Done** | Per-photo Remove button dropped; re-import replace remains |
| `TODO-008` | **Done** | Denser gallery: 4-column full-width grid, 4:3 thumbs |
| `TODO-009` | Pending | Honest (less flowery) Gemini neighborhood prompt |
| `TODO-010` | **Done** | Street View below map in Map tab; standalone SV tab removed |
| `library-visual-refresh` | **Done** | List-layout polish of `/` — see "Product decisions" #8 below |

Full write-ups: [`docs/TODO.md`](docs/TODO.md).  
**Before implementing overlays / area signals:** read [`docs/RESEARCH.md`](docs/RESEARCH.md) — do not re-research from scratch.

## Product decisions (locked)

1. **Ingest:** Zillow URL → store link + resolved address. No full MLS API. Listing HTML via `curl_cffi` (Chrome impersonation) for photos/details — Zillow blocks plain httpx.
2. **Street View:** Free Google `svembed` only; shown **below the map** on the Map tab in a collapsible expansion (open by default, shorter panel). No Maps Embed API keys for SV.
2b. **Map chrome:** Dark CARTO basemap (`apply_dark_basemap`); compact layer toggles above the map; single status line; Pin tools expansion below the map (collapsed). Fullscreen via `leaflet.fullscreen` (CDN + `fullscreenControl` options from `leaflet_map_kwargs()`), control near zoom; Escape / browser exit restores the in-tab map. No always-on Census tip — message only when Income toggle fails / key missing.
3. **Geocode:** Strip `UNIT`/`APT`/`#`/Suite; fallback query chain. Nominatim User-Agent: `Homebuy/0.1 (local research app)`.
4. **Optional env:** `GOOGLE_MAPS_API_KEY` (preferred geocoding); `CENSUS_API_KEY` (Map income choropleth — required for that toggle); `SOCRATA_APP_TOKEN` (optional, crime rate limits); `GEMINI_API_KEY` (Neighborhood AI).
5. **Theme accents:** Cyan `#00E5FF`, Magenta `#FF2BD6`, Lime `#B8FF3C`, Amber `#FFC107`.
6. **Neighborhood reviews:** Prefer **Zillow listing neighborhood** name; fallback Nominatim/Google; manual override. **Gemini** (`GEMINI_API_KEY`, model `gemini-2.5-flash-lite` by default) writes a cached overview paragraph (`neighborhood_gemini` / `neighborhood_gemini_for`) and a separate cached things-to-do list (`neighborhood_things_to_do` / `neighborhood_things_to_do_for`, key prefix `things_v1|`). Regenerating one does not wipe the other; both clear when the neighborhood override changes. Deep links only for Reddit/City-Data/Niche (no scrape); Niche uses a `/places-to-live/n/{hood}-{city}-{state}/` place URL when possible, else search. Notes in `neighborhood_notes`.
7. **Map overlays:** Layer toggles only (no Neighborhood chips). FEMA NFHL WMS flood; ACS `B19013` tract income (needs `CENSUS_API_KEY`); crime near pin for **all of LA County** (merges LAPD Socrata + Santa Monica CKAN; densest in those PDs) and Seattle. Also resolves from pin lat/lng when city is empty. Cache under `data/cache/`.
8. **Library page:** list layout, not a grid. Each row (`.hb-library-card`) is whole-card-clickable to `/property/{id}`; the Zillow link and delete icon stop click propagation (`js_handler` `stopPropagation`, combined with a Python `handler` for delete — needs NiceGUI ≥2.18 for both at once) so they don't also trigger navigation. Delete opens a confirm dialog (address snippet + Cancel/Delete) before calling `delete_property`. Price is pulled out of the meta string into its own neon `.hb-library-price` line; beds/baths/sqft/`$`-sqft render as `.hb-meta-chip` pills, home type/year/HOA as quieter `.hb-meta-chip--quiet` pills (city/state omitted — already in the address). No listing data yet → "Details pending — open and refresh listing". Filters (search/min/max price/min beds) live in a collapsed `ui.expansion("Filter")`; a muted "N homes" count sits next to the "Your homes" heading. Empty-DB and filtered-to-empty states have distinct copy.

## Working agreements for agents

- **After completing any user-facing feature or meaningful fix, update both `AGENTS.md` and `README.md`** in the same turn (status, how-to-use, decisions). Do not leave continuity docs stale.
- Prefer **parallel Task subagents** for independent features; declare file ownership to avoid merge fights (`models.py` / `property_service.py` / `pages.py` are hotspots).
- After UI/backend changes, **restart** `python -m app.main` (reload is off).
- Don’t commit unless the user asks.
- Don’t scrape in ways that need exploit kits; prefer official APIs where ToS matters (esp. Reddit).
- Keep modules thin; put shared logic in `app/core/`.

## Quick verify checklist

1. Library loads dark theme at http://127.0.0.1:8080 as a list of clickable home cards (thumb, neon price, meta chips); Filter is collapsed by default and a muted homes count shows next to the heading  
2. Paste a `/homedetails/..._zpid/` URL → Add home → photos + address + beds/price/sqft/HOA/year/type appear; card click opens the property page, Zillow link/delete icon on a card don't trigger that navigation, delete asks for confirmation  
3. Map pins (even with `UNIT` in the slug)  
4. Map tab: dark CARTO basemap; fullscreen control near zoom; flood/income/crime toggles; Street View expansion below map (free svembed, open by default); no always-on Census tip until Income is toggled without a key  
5. Financials shows neon charts on dark paper  
6. Neighborhood tab resolves a name, deep-link buttons open Reddit/City-Data/Niche/Google; Gemini overview + things-to-do buttons work when `GEMINI_API_KEY` is set  
7. `.\.venv\Scripts\pytest.exe -q` passes  

## Related docs

- `README.md` — user-facing run instructions  
- `.env.example` — optional keys  
- This file (`AGENTS.md`) — continuity for AI agents  
- `docs/RESEARCH.md` — map overlays + neighborhood research notes  
- `docs/TODO.md` — product backlog (listing scrape, area signals, Gemini sections)  
- `docs/BUGS.md` — deferred bugs / verify-later items 
