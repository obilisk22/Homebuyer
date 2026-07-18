# Homebuy

Modular Python app for researching homes linked from Zillow. Stores the **Zillow URL + address** only (no scraping of the full MLS). Dive deeper with Photos, Map (Street View + overlays), Neighborhood reviews, and Financials — each as a pluggable module.

**Continuing in a new AI session?** Read [`AGENTS.md`](AGENTS.md) first. Backlog: [`docs/TODO.md`](docs/TODO.md). Research: [`docs/RESEARCH.md`](docs/RESEARCH.md).

## Requirements

- Python 3.12+
- Optional: `GOOGLE_MAPS_API_KEY` only if you want Google geocoding for Map pins (otherwise free Nominatim is used). Street View uses a **free** iframe embed — no Cloud billing.
- Optional: `GEMINI_API_KEY` for Neighborhood tab AI overview + things-to-do (Google AI Studio / Gemini API).
- **Map income choropleth:** add `CENSUS_API_KEY` (free at https://api.census.gov/data/key_signup.html). Without it, the income toggle shows a setup message and stays off.
- Optional: `SOCRATA_APP_TOKEN` for higher rate limits on LA/Seattle crime overlays.

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

The `/` library page is a **list**, not a grid: each row is a wide clickable card with a larger 160×120 thumbnail (or a muted placeholder if no photo), the address, list price called out in neon cyan, and compact chips for beds/baths/sqft/`$`-per-sqft plus quieter chips for home type/year built/HOA. Homes with no listing data yet show "Details pending — open and refresh listing".

- Click anywhere on a card to open the property page. The **Open on Zillow** link and the delete icon stop the click from bubbling up, so they act independently.
- Delete asks for confirmation in a small dialog before removing the home.
- Search/price/beds filters live in a collapsed **Filter** expansion above the list; a muted count ("3 homes" / "1 home") shows next to the page title once results load.

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
| Crime near pin | LA / Seattle Socrata | Other cities: toggle disabled / message |

Responses are cached under `data/cache/` (gitignored with other `data/*`).

## Neighborhood reviews

The **Neighborhood** tab prefers the neighborhood name from the **Zillow listing**, with Nominatim/Google fallbacks and a manual override.

Click **Ask Gemini about this neighborhood** for a short AI overview (vibe + character). Separately, **Ask Gemini: things to do** generates a practical bullet list of nearby parks, food, walks, and activities. Requires `GEMINI_API_KEY` in `.env` (see `.env.example`). Optional `GEMINI_MODEL` (default `gemini-2.5-flash-lite`). Overview and things-to-do are cached independently per neighborhood/city.

Outbound deep links (Reddit, City-Data, Niche place pages, etc.) and your own notes live under **More links & notes**.

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

## Tests

```powershell
.\.venv\Scripts\pytest.exe
```
