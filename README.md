# Homebuy

Modular Python app for researching homes linked from Zillow. Stores the **Zillow URL + address** only (no scraping of the full MLS). Dive deeper with Photos, Map (Street View + overlays), Neighborhood reviews, and Financials — each as a pluggable module.

**Continuing in a new AI session?** Read [`AGENTS.md`](AGENTS.md) first. Backlog: [`docs/TODO.md`](docs/TODO.md). Research: [`docs/RESEARCH.md`](docs/RESEARCH.md).

## Requirements

- Python 3.12+
- Optional: `GOOGLE_MAPS_API_KEY` only if you want Google geocoding for Map pins (otherwise free Nominatim is used). Street View uses a **free** iframe embed — no Cloud billing.
- Optional: `GEMINI_API_KEY` for Neighborhood tab AI overview + things-to-do, and Financials tab breakdown/opinion (Google AI Studio / Gemini API).
- **Map income choropleth & Financials county tax estimate:** add `CENSUS_API_KEY` (free at https://api.census.gov/data/key_signup.html). Without it, the Map income toggle shows a setup message and Financials skips the ACS county tax estimate (Zillow annual tax → assessed × rate only, else $0). Insurance autofill is separate: Zillow annual insurance → state average-premium table scaled to list price.
- Optional: `SOCRATA_APP_TOKEN` for higher rate limits on LA County (LAPD Socrata + Santa Monica CKAN) and Seattle crime overlays.

## Setup (Windows)

```powershell
cd C:\Users\hheaf\Projects\homebuy
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

## Run

Prefer calling the venv interpreter directly (avoids PowerShell execution-policy issues with `Activate.ps1`):

```powershell
cd C:\Users\hheaf\Projects\homebuy
.\.venv\Scripts\python.exe -m app.main
```

Or double-click `run.bat`.

Opens at [http://127.0.0.1:8080](http://127.0.0.1:8080). A demo property is seeded on first launch.

## Add a home

1. Paste a Zillow listing URL  
2. Click **Add home**  

Address, photos, and listing details (beds, baths, price, sqft, HOA, year built, home type) are pulled from the link automatically. Use **Refresh listing details** on a property page to re-scrape. The **Photos** tab shows a dense click-to-expand gallery; use **Re-import (replace)** to refresh photos from Zillow.

## Library list view

The `/` library page is a **list**, not a grid: each wide clickable card shows a ~180×135 thumbnail (or placeholder), address, neon list price, chips for beds/baths/sqft/`$`-per-sqft, quieter type/year chips, and amber HOA when monthly HOA is $400+. Optional notes appear as a short teaser line.

- **Sort** (Newest / Price ↑ / Price ↓) sits beside a collapsed **Filter** expansion (search, min/max price, min beds). The Filter label shows how many filters are active.
- Card click opens the property. Use the **⋮** menu for **Open on Zillow** or **Delete…** (delete still confirms).
- When you already have homes, the long “paste a Zillow link…” hint is hidden so Add stays compact.
- On the **Photos** tab, pin any shot as the library thumbnail (locked through re-import when that photo survives). **Auto-pick again** clears the lock and re-runs the exterior-biased picker.

## Saving your work (Git)

| | |
|---|---|
| **GitHub** | https://github.com/obilisk22/Homebuyer |
| **Branch** | `main` |

```powershell
cd C:\Users\hheaf\Projects\homebuy
git status
git add -A
git commit -m "Describe what you finished."
git push
```

Ignored on purpose (not committed): virtualenv, `.env` secrets, SQLite DB, downloaded listing photos. See [`AGENTS.md`](AGENTS.md) for a Perforce-oriented cheat sheet.

## Map (Street View + overlays)

The **Map** tab shows a taller Leaflet pin map with a dark CARTO basemap to match the app theme. Use the fullscreen control (near zoom) to expand the map; Esc exits. Layer toggles sit above the map; Pin tools and Street View are below (Street View starts expanded). Free Street View uses `svembed` (no API key) in a desktop 16:9 panel.

Layer toggles (no Neighborhood summary chips):

| Toggle | Source | Notes |
|--------|--------|--------|
| Flood (FEMA) | NFHL WMS | No key |
| Median income (ACS) | Census ACS `B19013` tracts | Needs `CENSUS_API_KEY` |
| Median home value (ACS) | Census ACS `B25077` tracts | Needs `CENSUS_API_KEY` |
| Median age (ACS) | Census ACS `B01002` tracts | Needs `CENSUS_API_KEY` |
| Avg kids / HH (ACS) | `B09001` ÷ `B25003` tracts | Needs `CENSUS_API_KEY` |
| % owner-occupied (ACS) | `B25003` owner ÷ occupied | Needs `CENSUS_API_KEY` |
| Median year built (ACS) | Census ACS `B25035` | Needs `CENSUS_API_KEY` |
| Median gross rent (ACS) | Census ACS `B25064` | Needs `CENSUS_API_KEY` |
| % bachelor's+ (ACS) | `B15003` bachelor's+ / age 25+ | Needs `CENSUS_API_KEY` |
| Crime near pin | LA County (LAPD Socrata + Santa Monica CKAN) + Seattle | Hex density choropleth (count per cell); other cities: toggle disabled / message |

Responses are cached under `data/cache/` (gitignored with other `data/*`).

## Neighborhood reviews

The **Neighborhood** tab prefers the neighborhood name from the **Zillow listing**, with Nominatim/Google fallbacks and a manual override.

Click **Ask Gemini about this neighborhood** for a short AI overview (vibe + character). Separately, **Ask Gemini: things to do** generates a practical bullet list of nearby parks, food, walks, and activities. Requires `GEMINI_API_KEY` in `.env` (see `.env.example`). Optional `GEMINI_MODEL` (default `gemini-2.5-flash-lite`). Overview and things-to-do are cached independently per neighborhood/city.

Outbound deep links (Reddit, City-Data, Niche place pages, etc.) and your own notes live under **More links & notes**.

## Financials

The **Financials** tab is the PITI calculator (offer vs list, loan inputs, ownership costs) with neon Plotly charts. List price, HOA, property tax, and insurance are **autofilled from the Zillow listing** when you add a home or click **Refresh listing details** — loan terms (down payment, rate, term, closing costs) are never touched. Property tax resolves Zillow's annual tax → Zillow assessed value × rate → an ACS county effective-rate estimate; insurance resolves Zillow's annual insurance → a state average-premium estimate scaled to list price. When a value is estimated rather than taken straight from Zillow, a small caption appears under that field (e.g. *Estimated: ACS county*, *Estimated: CA avg premium*).

Below the charts, **Ask Gemini about these finances** produces a cached markdown Breakdown + Opinion from the *same calculator numbers* (not invented prices). Clearly labeled as AI opinion, not advice. Cache refreshes when you change assumptions (fingerprint) or click Regenerate. Same `GEMINI_API_KEY` / optional `GEMINI_MODEL` as Neighborhood.

## Extending with a new module

1. Create `app/modules/my_module.py`
2. Export a `MODULE`:

```python
from app.core.module_registry import ModuleSpec
from nicegui import ui

def render(prop, container: ui.element) -> None:
    with container:
        ui.label(prop.address)

MODULE = ModuleSpec(id="my_module", title="My Module", order=50, render=render)
```

3. Restart the app — the tab appears automatically.

Module first paints receive a fully eager-loaded, detached property from the property page. Treat it as read-only; open a new session and reload only when a module needs to persist or re-read changed data.

## Tests

```powershell
.\.venv\Scripts\pytest.exe
```
