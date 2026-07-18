# Homebuy

Modular Python app for researching homes linked from Zillow. Stores the **Zillow URL + address** only (no scraping of the full MLS). Dive deeper with Photos, Map, Street View, Neighborhood reviews, and Financials — each as a pluggable module.

**Continuing in a new AI session?** Read [`AGENTS.md`](AGENTS.md) first. Backlog: [`docs/TODO.md`](docs/TODO.md). Research: [`docs/RESEARCH.md`](docs/RESEARCH.md).

## Requirements

- Python 3.12+
- Optional: `GOOGLE_MAPS_API_KEY` only if you want Google geocoding for Map pins (otherwise free Nominatim is used). Street View uses a **free** iframe embed — no Cloud billing.
- Optional: `GEMINI_API_KEY` for Neighborhood tab AI overviews (Google AI Studio / Gemini API).

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

Address, photos, and listing details are pulled from the link automatically.

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

## Street View

Free embedded Street View iframe (no API key), shown in a desktop 16:9 panel. Coordinates are auto-resolved from the address when needed; the main Map tab can also set the pin. Optional open-in-Google buttons are included if the embed has no coverage.

## Neighborhood reviews

The **Neighborhood** tab prefers the neighborhood name from the **Zillow listing**, with Nominatim/Google fallbacks and a manual override.

Click **Ask Gemini about this neighborhood** to generate a short AI overview (vibe + local things to do). Requires `GEMINI_API_KEY` in `.env` (see `.env.example`). Optional `GEMINI_MODEL` (default `gemini-2.5-flash-lite`). Summaries are cached per neighborhood/city.

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
