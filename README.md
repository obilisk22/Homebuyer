# Homebuy

Modular Python app for researching homes linked from Zillow. Stores the **Zillow URL + address** only (no scraping of the full MLS). Dive deeper with Photos, Map (Street View + overlays), Neighborhood reviews, and Financials — each as a pluggable module.

**Continuing in a new AI session?** Read [`AGENTS.md`](AGENTS.md) first. Backlog: [`docs/TODO.md`](docs/TODO.md). Research: [`docs/RESEARCH.md`](docs/RESEARCH.md).

## Requirements

- Python 3.12+
- Optional: `GOOGLE_MAPS_API_KEY` only if you want Google geocoding for Map pins (otherwise free Nominatim is used). Street View uses a **free** iframe embed — no Cloud billing.
- Optional: `GEMINI_API_KEY` for Neighborhood tab AI overview + things-to-do, Financials tab breakdown/opinion, and Photos tab overall property take (Google AI Studio / Gemini API). Neighborhood uses `GEMINI_MODEL` (default `gemini-3.1-flash-lite`). Financials and Photos use `GEMINI_FINANCIAL_MODEL` → else `GEMINI_MODEL` → else `gemini-2.5-flash-lite` (2.5 keeps free-tier URL context + Google Search working).
- **Census Bureau API (`CENSUS_API_KEY`):** free at https://api.census.gov/data/key_signup.html. Powers all Map ACS tract choropleths (income, home value, median age, avg kids, % owner-occupied, year built, gross rent, % bachelor's+), Financials ACS county property-tax fallback, and buy-vs-rent rent-growth CAGR from county median gross rent. Without it, ACS map toggles show a setup message, Financials skips the ACS county tax estimate (Zillow annual tax → assessed × rate only, else $0), and rent growth defaults to **3%/yr**. Insurance autofill is separate: scrape Zillow's modeled homeowners insurance when the listing HTML includes it → otherwise state average-premium table scaled to list price.
- Optional: `SOCRATA_APP_TOKEN` for higher rate limits on LA County (LAPD Socrata + Santa Monica CKAN) and Seattle crime overlays, and on LA / Seattle / Austin building-permit lookups.
- No key needed for the library **no fixed broadband** risk chip — it uses free `geo.fcc.gov` block lookup + Living Atlas BDC UniqueProviders* (DSL/cable alone does not flag; only total absence of fixed terrestrial service).
- No key needed for the Neighborhood tab's **Assigned schools** quality badge — it uses the free CA School Dashboard (CDE Academic Indicator downloadable data, cached locally) + a Niche parent-review deep link.

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

Opens at [http://127.0.0.1:8080](http://127.0.0.1:8080) in your **browser**. A demo property is seeded on first launch. Day-to-day iteration stays in the browser.

### Desktop window (optional)

To open the same app in a native window (pywebview / WebView2) without packaging:

```powershell
.\run-native.bat
# or:  $env:HOMEBUY_NATIVE=1; .\.venv\Scripts\python.exe -m app.main --native
```

### Windows installer / packaged exe

See [`docs/PACKAGING.md`](docs/PACKAGING.md). Short version:

```powershell
.\packaging\build_windows.ps1            # → dist\Homebuy\Homebuy.exe
.\packaging\build_windows.ps1 -Installer # → dist\installer\Homebuy-Setup-0.1.0.exe (needs Inno Setup 6)
```

Installed builds write DB/uploads/cache to `%LOCALAPPDATA%\Homebuy\` and load optional keys from `%LOCALAPPDATA%\Homebuy\.env`. Enter keys in the app via the **key icon** on the Library header (API keys dialog) — leave a field blank to keep the current value, or Clear to remove it. Do not ship your personal `.env` with the installer.

## Add a home

1. Paste a Zillow listing URL  
2. Click **Add home**  

Address, photos, and listing details (beds, baths, price, sqft, HOA, year built, home type) are pulled from the link automatically. After the pin is set, photo downloads and area-signal lookups (nearby / permits / broadband / market) run in parallel so Add finishes sooner; signal failures never block the save. Imported photos store a mid-size file plus a small WebP thumb sidecar for library/header cards (gallery still uses the mid-size file). Use **Refresh listing details** on a property page to re-scrape listing fields. **Edit listing details** is a muted collapsed control under the header actions (not competing with the tabs). Nearby proximity icons also appear on the property header when cached. The **Photos** tab is a dense click-to-expand gallery (photos come from the initial add; pin any shot as the library thumbnail) plus an optional **Ask Gemini** overall property take (Zillow URL context; needs `GEMINI_API_KEY`).

## Library list view

The `/` library page is a **list**, not a grid: each wide clickable card shows a photo that stretches to match the text column, a large Akira street address, quieter Creato list price, chips for beds/baths/sqft/`$`-per-sqft, quieter type/year chips, and amber HOA when monthly HOA is $400+. When Financials exist, a quiet **PITI**/mo caption and **Growth N%/yr** (amber when under 3%, lime when over 6%) appear under the chips. Street addresses use a slightly smaller Akira line; condo unit markers (`APT`/`UNIT`/etc.) display as a compact smaller `#…` suffix. When a home is geocoded, **nearby proximity icons** may appear on the **bottom-right of the library card** (not over the photo) — OSM Overpass for highway, transit, playground, grocery, and shelter; with `GOOGLE_MAPS_API_KEY` set, Google Places refines grocery and shelter matches (merged with OSM). Icons show only when within range (highway ≤800 ft, transit/grocery ≤0.5 mi, playground ≤0.9375 mi, shelter ≤0.5 mi); magenta flags risks (highway/shelter), lime marks amenities; hover for distance and nearest name; **click opens Google Maps** directions from the home to that specific place (place_id when available, else name@coords — not a category search) in a new tab (without opening the property card). Magenta listing-risk chips in that same row: **no Central AC** when the Zillow listing clearly lacks central air; **no fixed broadband** when FCC BDC reports zero fixed terrestrial service (no API key; DSL/cable alone does not flag); and **Center townhome** when the listing is a Townhouse with clear mid-row / interior-unit language (end unit or uncertain → no chip). Homes in **Los Angeles / Seattle / Austin** may also show an amber **high permit activity** chip (≥8 structural/electrical/demolition-ish permits within ~0.25 mi in 24 months). A lime **Active market** chip appears when the home’s ZIP had elevated recent Redfin monthly sales (`homes_sold ≥ max(12, national P75)`). Stale nearby / permit / broadband / market lookups refresh in **one coalesced background job** after the cards paint; only chip rows that changed are patched (no full list rebuild). Optional notes appear as a short teaser line. Page chrome (title, Add, Sort/Filter, empty states) uses the same Creato dark theme as the cards.

Card click opens the property with **Photos** mounted first; Map, Neighborhood, and Financials load on first select (Financials rate/maint/utilities backfill runs off the UI thread when that tab opens).

## Theme / fonts

Dark near-black UI with cyan hierarchy accents (glow marks priority: active tabs, focus, primary CTAs — not every surface). **Buttons, tabs, and map overlay chips** use dark neumorphism; neon only when active/on. Body text uses **Creato Display**; street addresses / brand use **Akira Expanded**. Download both from DaFont and drop the `.otf` files into `app/static/fonts/` (see that folder’s README). Creato is OFL (safe to commit); Akira is personal-use only and is gitignored.

- **Sort** sits beside a collapsed **Filter** expansion. Filters apply on Enter or after a short pause while typing; the open button is **Apply**. The collapsed label shows how many filters are active.
- **Export** downloads CSV or JSON of the full library + financial fields.
- Click **Homebuy** (or the home icon) to return to the library.
- Card click opens the property (Photos first; other tabs lazy). Use the **⋮** menu for **Open on Zillow** or **Delete…** (delete still confirms).
- When you already have homes, the long “paste a Zillow link…” hint is hidden so Add stays compact.
- On the **Photos** tab, pin any shot as the library thumbnail. Photos are imported when you add the home (no re-import / upload controls on this tab). Use **Ask Gemini** for a short overall property take from the Zillow listing URL.
- **Neighborhood**, **Financials**, and **Photos** have in-tab **Ask Gemini** / **Regenerate** (AI opinion, not advice). There is no property-header bulk Gemini button.

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

Agent turns also **auto-commit locally** when they finish (Cursor `stop` hook). That never pushes — run `git push` yourself when you want GitHub updated.

## Map (Street View + overlays)

The **Map** tab shows a taller Leaflet pin map with a dark CARTO basemap to match the app theme. Use the fullscreen control (near zoom) to expand the map; Esc exits. Layer toggles sit above the map; Pin tools and Street View are below (Street View starts expanded). Free Street View uses `svembed` (no API key) in a compact desktop 16:9 panel. When the home is pinned, open links jump to Google Maps, Street View, or Google Earth (web deep link, new tab).

Layer toggles are exclusive (one overlay at a time; turning another on clears the previous):

| Toggle | Source | Notes |
|--------|--------|--------|
| Flood (FEMA) | NFHL WMS | No key |
| Zoning | City of LA (ZIMAS 1102 citywide), Santa Monica (SCAG), LA County DRP | ACS-style slim polygons (~2.8 mi radius); coords quantized for smaller toggles; other cities: disabled / message |
| Wildfire | USFS Wildfire Hazard Potential 2023 WMS | No key; long-term hazard classes |
| AQI | Open-Meteo US AQI | Hex grid near pin; no key |
| Schools | NCES CCD / Locale / EDGE public school points | ~4 mi radius markers + legend; no GreatSchools. (Assigned Elementary/Middle/High schools for a home live on the **Neighborhood** tab, not this overlay — see below.) |
| Sale price | Redfin Data Center ZIP median → ZCTA | First load may ingest the national TSV once (gzip disk + process memo; concurrent callers singleflight) |
| Median income (ACS) | Census ACS `B19013` tracts | Needs `CENSUS_API_KEY` |
| Median home value (ACS) | Census ACS `B25077` tracts | Needs `CENSUS_API_KEY` |
| Median age (ACS) | Census ACS `B01002` tracts | Needs `CENSUS_API_KEY` |
| Avg kids / HH (ACS) | `B09001` ÷ `B25003` tracts | Needs `CENSUS_API_KEY` |
| % owner-occupied (ACS) | `B25003` owner ÷ occupied | Needs `CENSUS_API_KEY` |
| Median year built (ACS) | Census ACS `B25035` | Needs `CENSUS_API_KEY` |
| Median gross rent (ACS) | Census ACS `B25064` | Needs `CENSUS_API_KEY` |
| % bachelor's+ (ACS) | `B15003` bachelor's+ / age 25+ | Needs `CENSUS_API_KEY` |
| Crime near pin | LA County (LAPD Socrata + Santa Monica CKAN) + Seattle | Hex density choropleth (count per cell); other cities: toggle disabled / message |

Responses are cached under `data/cache/` (gitignored with other `data/*`) via a shared cache platform (disk JSON/gzip, process memo, singleflight, GeoJSON quantize for zoning/ACS).

## Neighborhood reviews

The **Neighborhood** tab prefers the neighborhood name from the **Zillow listing**, with Nominatim/Google fallbacks and a manual override.

**Assigned schools:** three cards — Elementary, Middle, High — show the schools a pinned home is zoned for, resolved by checking the pin against **LAUSD attendance-boundary GIS** (point-in-polygon against the district's public ArcGIS attendance layers, then matching the zone to a named school). This is **v1 LAUSD-only**; homes outside LAUSD show a "not available for this district yet" message instead of a wrong guess. Each card also shows a free **CA School Dashboard** color badge (Blue/Green/Yellow/Orange/Red, from the CDE Academic Indicator downloadable data keyed by CDS code) plus **Dashboard** and **Niche** (parent reviews) deep-link buttons — no API key needed; if the color lookup misses, the links still work. This is separate from the Map tab's **Schools** overlay (nearby NCES points for any area) — no "Nearby schools" list on the map anymore; that lookup moved here.

Click **Ask Gemini about this neighborhood** for a short AI overview (vibe + character). Separately, **Ask Gemini: things to do** generates a practical bullet list of nearby parks, food, walks, and activities. Requires `GEMINI_API_KEY` in `.env` (see `.env.example`). Optional `GEMINI_MODEL` (default `gemini-3.1-flash-lite`). Prompts include the home’s exact street address plus neighborhood/city; overview and things-to-do are cached independently.

Outbound deep links (Reddit, City-Data, Niche place pages, etc.) and your own notes live under **More links & notes**.

## Financials

The **Financials** tab is the PITI calculator with neon Plotly charts. It mounts on first select (not at property open); mortgage-rate / maintenance / utilities backfill runs in the background then. Always visible: **Your deal** (offer + down in **dollars** — amber warning if under 20%, PMI may apply) and **Buy vs rent** (comparable rent + **Rent control**). **Loan**, **Ownership costs** (tax, insurance, HOA, maintenance, **utilities**), and advanced buy-vs-rent knobs sit in collapsed expansions. Each field has a quiet **?** help tooltip (how the default was calculated) and a **revert** control to restore the product/autofill baseline. Press **Enter** in any field to recalculate (or use Recalculate). The hero **Monthly payment** is PITI **plus** maintenance **and** utilities.

List price, HOA, property tax, insurance, rent, appreciation, **maintenance**, and **utilities** are **autofilled** when you add a home or click **Refresh listing details** — loan terms (down payment, rate, term, closing costs) are never touched. Rent comes from Zillow's `rentZestimate` when present; if the listing has no rent estimate, comparable rent defaults to **$5,300**/mo (caption `Default`). Appreciation blends FHFA ZIP5 ~10-year CAGR and Zillow's decade appreciation when both exist (defaults to **3%/yr** if neither is available). **Maintenance** blends an age-based budget reserve (% of price averaged with $/sqft) with Angi national typical spend, then scales the labor-like legs by a **state cost index** (California **×1.15**). **Utilities** estimate electric+gas from provider territory (LADWP vs SCE + SoCalGas in LA-area) × sqft × age factor, plus water/trash. Edit any autofilled field to override; source captions appear under each field. FHFA downloads the public ZIP5 HPI workbook on first use (no extra API key); it is cached under `data/cache/fhfa/` for about 30 days and automatically finds its header after the workbook's title and notes rows.

**Rent growth** in the buy-vs-rent chart: check **Rent control** to assume **2%/yr** rent increases. When unchecked, growth is filled from Census ACS county median gross rent (**B25064**) ~5-year CAGR at the property pin (needs `CENSUS_API_KEY` in `.env`); if ACS is unavailable, growth defaults to **3%/yr**. A caption under comparable rent shows the growth rate and source. Owner PITI stays flat over the loan term; comparable rent **and** ownership maintenance/utilities rise with that growth rate in the projection.

Property tax resolves Zillow's annual tax → Zillow assessed value × rate → an ACS county effective-rate estimate; insurance prefers Zillow's on-page homeowners estimate when present in the listing HTML (including nested / alternate field names), otherwise a state average-premium estimate scaled to list price. When a value is estimated rather than taken straight from Zillow, a small caption appears under that field (e.g. *Estimated: ACS county*, *Estimated: CA avg premium*, *Estimated: age blend · CA×1.15*).

Two charts: **monthly payment mix** (pie) and **Buy vs rent + invest (net worth)**. Both paths invest leftover **housing budget** (default **$13,000**/mo). Buying uses an after-tax ownership cost (PITI + maint + utilities, with mortgage interest + SALT-capped property tax at a CA MFJ-style **41%** marginal rate) and subtracts capital-gains tax on a hypothetical sale after a **$500k** primary-residence exclusion (**24%** CG rate default). Cyan = buy (sale proceeds − loan − CG tax + buyer surplus portfolio); magenta = rent + invest (cash-to-close + renter surplus). Caption shows budget, tax, and growth assumptions. Advanced knobs (appreciation, invest return, sell cost, budget, tax rates) live under **Advanced buy vs rent**.

Below the charts, the **Gemini financial take** opens the subject Zillow URL plus your other library Zillow links (Gemini **URL context** tool) and writes opinion on why pricing looks as it does, market/location, and buy vs rent — not a restatement of your calculator. Cache key is `fin_v4` over those URLs. Same `GEMINI_API_KEY`; model resolves `GEMINI_FINANCIAL_MODEL` → else `GEMINI_MODEL` → else `gemini-2.5-flash-lite` (2.5 keeps free-tier URL context + Google Search working). Note: if Zillow blocks the URL fetch, Gemini may return a thin/empty take — regenerate or check the listing links.

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

Modules mount **lazily** on first tab select (default Photos mounts immediately). First paint receives a detached property from the property page — treat it as read-only; open a new session and reload only when a module needs to persist or re-read changed data. Long I/O (Financials `ensure_financial` / PMMS, Map geocode, Neighborhood schools) stays on `run.io_bound` when that tab mounts.

## Tests

```powershell
.\.venv\Scripts\pytest.exe
```
