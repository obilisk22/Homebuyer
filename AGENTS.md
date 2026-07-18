# Homebuy — Agent Continuity Guide

> Read this first when starting a new agent session on this project.
> Last updated: 2026-07-18 (Library iteration 2 — sort, HOA highlight, thumb lock)

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
| Financials Gemini commentary | `app/core/gemini_financial.py` |
| Library thumbnail pick | `app/core/thumbnail.py` |
| Mortgage math | `app/core/finance.py` |
| Map overlays | `app/core/{census_acs,fema_flood,crime_socrata,crime_density,overlay_cache}.py` |
| Dark basemap | `app/core/map_basemap.py` (CARTO `dark_all` after `ui.leaflet`) |
| Modules | `app/modules/{gallery,map_view,neighborhood_reviews,financial}.py` (+ `street_view.py` helpers, no tab) |
| Env template | `.env.example` |

### Data model (high level)

**Property:** `address`, `zillow_url`, `list_price`, `beds`, `baths`, `sqft`, `hoa_fee`, `year_built`, `home_type`, `city`, `state`, `zip_code`, `latitude`, `longitude`, `thumbnail_photo_id`, `notes`, `neighborhood_name`, `neighborhood_source`, `neighborhood_override`, `neighborhood_notes`, `neighborhood_gemini`, `neighborhood_gemini_for`, `neighborhood_things_to_do`, `neighborhood_things_to_do_for`, `financial_gemini`, `financial_gemini_for`

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
- [x] Financials: offer vs list, PITI + PMI, neon Plotly charts + Gemini breakdown/opinion (cached by assumption fingerprint)
- [x] Library search/filters (price, beds, city/address)
- [x] Cyberpunk dark theme
- [x] Add-home is Zillow URL only (address from listing/URL)
- [x] Initial Git commit + push to https://github.com/obilisk22/Homebuyer (`main`)
- [x] Neighborhood Reviews: Zillow neighborhood name + Gemini overview + things-to-do list + deep links/notes
- [x] Map overlays (slice): FEMA flood WMS + ACS median income choropleth + LA/Santa Monica/Seattle crime (hex density choropleth)
- [x] Street View folded into Map tab (map on top, free svembed below; no standalone SV tab)
- [x] Map tab Direction 1 polish: CARTO dark basemap, compact layer bar, taller map, quieter status, Pin tools + collapsible Street View below map
- [x] Map fullscreen control (leaflet.fullscreen near zoom; survives redraw)
- [x] Richer Zillow listing scrape: beds, price, sqft, HOA, year built, home type (library + header + edit)
- [x] Library visual refresh + iteration 2: list cards (~180×135 thumb), neon price, chips + amber HOA ≥$400, notes teaser, ⋮ menu (Zillow/Delete), sort + filter active count, compact Add when nonempty; lockable library thumb from Photos + stronger exterior auto-pick
- [x] TODO-006 codebase cleanup (2026-07-18): dead helpers removed, single Zillow HTML fetch on add, batched photo import, fewer redundant DB loads, overlay cache prune on miss, lazy Plotly import — features unchanged

## In progress / next (as of last session)

| ID | Status | Notes |
|----|--------|-------|
| `map-overlays-impl` | **Partial** | Flood + ACS income + LA County (LAPD Socrata + Santa Monica CKAN) + Seattle crime hex density; deferred Redfin / ACS value / AQI / fire |
| `TODO-002` | **Partial** | Income + flood + LA County/Seattle crime on Map; still pending AQI, fire, avg home price |
| `TODO-009` | Pending | Honest (less flowery) Gemini neighborhood prompt |

Full write-ups: [`docs/TODO.md`](docs/TODO.md).  
**Before implementing overlays / area signals:** read [`docs/RESEARCH.md`](docs/RESEARCH.md) — do not re-research from scratch.

## Product decisions (locked)

1. **Ingest:** Zillow URL → store link + resolved address. No full MLS API. Listing HTML via `curl_cffi` (Chrome impersonation) for photos/details — Zillow blocks plain httpx.
2. **Street View:** Free Google `svembed` only; shown **below the map** on the Map tab in a collapsible expansion (open by default, shorter panel). No Maps Embed API keys for SV.
2b. **Map chrome:** Dark CARTO basemap (`apply_dark_basemap`); compact layer toggles above the map; single status line; Pin tools expansion below the map (collapsed). Fullscreen via `leaflet.fullscreen` (CDN + `fullscreenControl` options from `leaflet_map_kwargs()`), control near zoom; Escape / browser exit restores the in-tab map. No always-on Census tip — message only when Income toggle fails / key missing.
3. **Geocode:** Strip `UNIT`/`APT`/`#`/Suite; fallback query chain. Nominatim User-Agent: `Homebuy/0.1 (local research app)`.
4. **Optional env:** `GOOGLE_MAPS_API_KEY` (preferred geocoding); `CENSUS_API_KEY` (Map income choropleth — required for that toggle); `SOCRATA_APP_TOKEN` (optional, crime rate limits); `GEMINI_API_KEY` (Neighborhood AI + Financials commentary).
5. **Theme accents:** Cyan `#00E5FF`, Magenta `#FF2BD6`, Lime `#B8FF3C`, Amber `#FFC107`.
6. **Neighborhood reviews:** Prefer **Zillow listing neighborhood** name; fallback Nominatim/Google; manual override. **Gemini** (`GEMINI_API_KEY`, model `gemini-2.5-flash-lite` by default) writes a cached overview paragraph (`neighborhood_gemini` / `neighborhood_gemini_for`) and a separate cached things-to-do list (`neighborhood_things_to_do` / `neighborhood_things_to_do_for`, key prefix `things_v2|`). Regenerating one does not wipe the other; both clear when the neighborhood override changes. Deep links only for Reddit/City-Data/Niche (no scrape); Niche uses a `/places-to-live/n/{hood}-{city}-{state}/` place URL when possible, else search. Notes in `neighborhood_notes`.
6b. **Financials Gemini:** Commentary only — PITI / Plotly remain source of truth. Prompt is built from `summarize()` outputs + `FinancialAssumptions` (and listing context). Cached on Property as `financial_gemini` / `financial_gemini_for` with fingerprint `fin_v1|list|offer|down|rate|term|tax|ins|hoa|closing`. UI: **Ask Gemini about these finances** + Regenerate below charts; labeled as AI opinion / not advice; requires list or offer price.
7. **Map overlays:** Layer toggles only (no Neighborhood chips). FEMA NFHL WMS flood; ACS `B19013` tract income (needs `CENSUS_API_KEY`); crime near pin for **all of LA County** (merges LAPD Socrata + Santa Monica CKAN; densest in those PDs) and Seattle — rendered as a **hex density choropleth** (incident counts per cell), not individual report dots. Also resolves from pin lat/lng when city is empty. Cache under `data/cache/`.
8. **Library page:** list layout, not a grid. Cards (`.hb-library-card`, ~180×135 thumb) are whole-card-clickable; **Open on Zillow** / **Delete…** live in a ⋮ overflow menu (stopPropagation). Delete still confirms. Price is neon `.hb-library-price`; primary chips for beds/baths/sqft/`$`-sqft; quieter chips for type/year; HOA ≥ $400/mo uses amber `.hb-meta-chip--hoa-high`. Notes teaser (truncated) when set. Sort select: Newest / Price ↑ / Price ↓. Filter expansion shows “N active” when filters set. Compact Add (hide helper line) when the DB already has homes. **Thumbnails:** auto-pick prefers exterior (interior keyword penalties); `thumbnail_locked` + Photos pin (“Use as library thumbnail”) / **Auto-pick again**.

## Working agreements for agents

- **After completing any user-facing feature or meaningful fix, update both `AGENTS.md` and `README.md`** in the same turn (status, how-to-use, decisions). Do not leave continuity docs stale.
- Prefer **parallel Task subagents** for independent features; declare file ownership to avoid merge fights (`models.py` / `property_service.py` / `pages.py` are hotspots).
- After UI/backend changes, **restart** `python -m app.main` (reload is off).
- Don’t commit unless the user asks.
- Don’t scrape in ways that need exploit kits; prefer official APIs where ToS matters (esp. Reddit).
- Keep modules thin; put shared logic in `app/core/`.

## Quick verify checklist

1. Library loads dark theme at http://127.0.0.1:8080 as a list of clickable home cards (larger thumb, neon price, meta chips, ⋮ menu); Sort + collapsed Filter with active count; muted homes count next to the heading  
2. Paste a `/homedetails/..._zpid/` URL → Add home → photos + address + beds/price/sqft/HOA/year/type appear; card click opens the property; menu Zillow/Delete don't navigate the card; delete confirms; Photos pin sets library thumb  
3. Map pins (even with `UNIT` in the slug)  
4. Map tab: dark CARTO basemap; fullscreen control near zoom; flood/income/crime toggles; Street View expansion below map (free svembed, open by default); no always-on Census tip until Income is toggled without a key  
5. Financials shows neon charts on dark paper; Gemini financial take section Ask / Regenerate works when `GEMINI_API_KEY` is set  
6. Neighborhood tab resolves a name, deep-link buttons open Reddit/City-Data/Niche/Google; Gemini overview + things-to-do buttons work when `GEMINI_API_KEY` is set  
7. `.\.venv\Scripts\pytest.exe -q` passes  

## Related docs

- `README.md` — user-facing run instructions  
- `.env.example` — optional keys  
- This file (`AGENTS.md`) — continuity for AI agents  
- `docs/RESEARCH.md` — map overlays + neighborhood research notes  
- `docs/TODO.md` — product backlog (listing scrape, area signals, Gemini sections)  
- `docs/BUGS.md` — deferred bugs / verify-later items 
