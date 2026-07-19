# Research notes — Homebuy

Captured 2026-07-17 from research agents. **Do not re-research from scratch** unless these go stale; implement from here.

---

## Map overlays

Source: [Map overlays research v2](323317c3-1601-4d1f-8acb-0a1211070c19)

### Recommended v1 (1–2 days, free)

1. **Income choropleth** — Census ACS `B19013` (tract or ZCTA) + TIGER/cartographic boundaries  
2. **Home value choropleth** — ACS `B25077` (owner-estimated value, not sale price)  
3. **Sale-price choropleth** — Redfin Data Center ZIP median sale → join ZCTA polygons  
4. **Flood toggle** — FEMA NFHL WMS (`L.tileLayer.wms`)  
5. **Crime near pin** — LA / Seattle Socrata SODA, bbox + recent window, cluster/heat  

**Day-2 bonuses:** NCES school points; EPA National Walkability Index.

**Library nearby badges (2026-07-18, not Map overlays):** OSM Overpass around the pin for highway/transit/playground/grocery/shelter; optional Google Places Nearby Search for grocery + shelter when `GOOGLE_MAPS_API_KEY` is set. Cached per property + raw responses ~7d — see `app/core/nearby_signals.py` and TODO-025.

### Keys

| Key | Needed? |
|-----|---------|
| `CENSUS_API_KEY` | Yes for live ACS |
| `SOCRATA_APP_TOKEN` | Optional (rate limits) |
| FEMA / Redfin download / NCES / EPA | No key |

### Avoid

CrimeGrade scraping, GreatSchools paid API, FBI CDE for neighborhood maps, Zillow for overlay layers, SpotCrime/CrimeoMeter paid APIs.

### Also noted (optional later)

- **Crime Open Database (CODE)** — historical multi-city CC-BY dump; prefer live Socrata for LA/Seattle  
- **USGS seismic hazard** — useful CA bonus tiles  
- **Transitland / Walk Score** — pin enrichment, not choropleths  
- **FHFA HPI** — appreciation indexes, not dollar medians  

### Stack shorthand

**Census ACS + Redfin ZIP + FEMA WMS + city Socrata crime** → Leaflet toggles on existing map; cache server-side; never load nationwide crime into the browser.

### Implemented (2026-07-18 slice)

Shipped on Map tab toggles (no Neighborhood chips): FEMA NFHL WMS flood; **Zoning** (City of LA ZIMAS **`1102` citywide** — not Chapter 1A `1101` pockets; Santa Monica via SCAG `Zoning_poly_LA`; LA County DRP unincorporated + SCAG fallback; ACS-scale bbox ~0.04° + ArcGIS pagination) as ACS-style GeoJSON (`zoning_gis.py`); ACS choropleths for median income / home value / age / kids / owner% / year built / rent / bachelor's+ via `census_acs.py` (`CENSUS_API_KEY`); LA County + Seattle crime as a **hex density choropleth** (`crime_density.py`); **Schools** via NCES EDGE ArcGIS REST bbox (~4 mi, `schools_nces.py`) map markers + legend (no nearest-schools list — see "Assigned schools" below for the Neighborhood-tab per-home lookup); **Wildfire** USFS WHP 2023 WMS (`wildfire_whp.py`); **AQI** Open-Meteo US AQI hex grid (`air_quality.py`, no key); **Sale price** Redfin ZIP tracker → ZCTA join (`redfin_sales.py`). Cache: `data/cache/`. Street View merged into Map tab (TODO-010).

### Schools (NCES) — Map overlay

- Primary: CCD `Schools_Points_2025_CCD` MapServer layer 4 (`nces.ed.gov/arcgis`) — includes `SLEVEL_TEXT`.
- Fallbacks: LocaleViewer `PublicSchools24_25`, then EDGE `EDGE_GEOCODE_PUBLICSCH_2425` / `2324` on `opengis` (often 500).
- Envelope query ~4 mi — **not** a full national download.
- No GreatSchools paid API. This overlay is nearby-points only; it does not answer "which school is this home zoned for."

### Assigned schools (LAUSD attendance) — Neighborhood tab, shipped 2026-07-18

**Attendance-boundary lookup is now in scope, LAUSD-only.** Distinct from the NCES Map overlay above: instead of "schools near this point," this answers "which Elementary/Middle/High school is this address zoned into."

- **Source:** LAUSD's public `LAUSD_Schools` ArcGIS MapServer (`maps.lacity.org/lahub/rest/services/LAUSD_Schools/MapServer`) — no key, no paid GreatSchools/attendance-boundary API.
  - Attendance polygons: layers **4** (elementary), **5** (middle), **6** (high) — point query (`geometryType=esriGeometryPoint`, `spatialRel=esriSpatialRelIntersects`) returns the zone's `geometry.rings` plus a key attribute, but **no school name** on the attendance feature itself.
  - **Name resolve trick:** query layer **0** (school points) within a 3-mile buffer of the pin, filtered by `MAP_TYPE` (`ES`/`MS`/`HS`), then keep only the candidate points that are themselves inside the attendance polygon rings (ray-cast point-in-polygon) — the LAUSD-recommended way to turn an attendance key into a name, since the layer doesn't expose it directly. Ties (rare) break by haversine distance to the pin.
- **Geometry:** plain ray-casting point-in-polygon (`app/core/school_zones.py::point_in_ring` / `point_in_polygon`), outer ring + hole support — no shapely dependency needed for this simple case.
- **Coverage:** LAUSD only for v1 (registry-shaped so another district could be added later). A rough LAUSD bbox (`33.70–34.35, -118.70–-118.15`) distinguishes "outside LAUSD" from "inside LAUSD but a rare boundary gap" when zero attendance layers match.
- **Quality layer:** SchoolDigger REST v2.4 (free DEV/TEST tier, `appID`/`appKey`) — search by name + level, prefer the result whose city matches, then a detail call for `rankHistory` (star rating) and parent `reviews` (average/count/quote). Best-effort only: missing keys, no name match, or any request error all fall back to showing the school with no rating, never a hard failure.
- **Cache:** ~7 days under `data/cache/school_zones/` (attendance + name resolve) and `data/cache/schooldigger/` (search + detail), both via the existing `overlay_cache` helper.
- **Avoid:** paid attendance-zone APIs (SchoolDigger's own zone lookup is a paid tier), GreatSchools API, guessing a "nearest school" as the assigned one (attendance boundaries are not proximity-based).
- **Placement:** Neighborhood tab, not the Map — this is per-home detail, not a spatial overlay layer. The Map tab's old "Nearby schools" distance list was removed; the Schools toggle (NCES markers) stays as the nearby-points overlay.

### Wildfire + AQI

- Wildfire: USFS RMRS WHP classified WMS (same pattern as FEMA flood).
- AQI: Open-Meteo (no key) preferred over AirNow/OpenAQ registration.

### Redfin sale choropleth

- Public S3 gzip TSV `zip_code_market_tracker.tsv000.gz`; stream once → slim ZIP→median cache (~7d); join TIGER ZCTA near pin; muted fill when join misses.

---

## Neighborhood reviews / locals’ opinions

Source: [Neighborhood reviews research v2](3a6daec2-ae9b-4383-a1e6-1caf7b562d47)

### Recommended v1 (1–2 days)

1. **Resolve neighborhood name:** Zillow HTML already fetched → Nominatim reverse (cached) → optional Google → manual override  
2. **Module UI:** show name + editable override  
3. **Deep links only** (no scrape): Reddit search `"{neighborhood}" {city}`, city housing subreddit guesses, City-Data / Niche / Google `site:reddit.com`  
4. **Optional:** paste Reddit URL → official embed iframe  
5. **User notes** textarea (first-party, always safe)  
6. OSM/Nominatim attribution + disclaimer  

### Avoid

Scraping Reddit / City-Data / Niche / AreaVibes / Nextdoor; Census tract labels as neighborhood names; bulk Reddit harvest without approved API.

### Keys

None required for v1. Optional: existing `GOOGLE_MAPS_API_KEY`, later Reddit developer app (if approved), Nextdoor partner, AreaVibes widget.

### v2 stretch

Reddit Data API (titles/permalinks only), Nextdoor partner API, city GIS neighborhood polygons, AreaVibes widget, tie-in to map overlay context.

---

## Suggested build order

1. Neighborhood Reviews module (deep links + name resolver) — faster UX win  
2. Map overlays v1 (Census + flood + crime bbox) — needs `CENSUS_API_KEY`  
3. Redfin sale choropleth + school/walkability bonuses  
