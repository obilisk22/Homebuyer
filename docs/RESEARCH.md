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

**Library nearby badges (2026-07-18, not Map overlays; fixed TODO-036 2026-07-19):** OSM Overpass around the pin for highway/transit/playground/grocery/shelter; optional Google Places Nearby Search for grocery + shelter when `GOOGLE_MAPS_API_KEY` is set (merged with OSM). Thresholds: highway ≤800 ft, transit/grocery ≤0.5 mi, playground ≤0.75 mi, shelter ≤0.5 mi. Cached per property + raw responses ~7d — see `app/core/nearby_signals.py` and TODO-025 / TODO-036.

**BTS National Transportation Noise Map (TODO-041, 2026-07-19):** No public WMS — use ArcGIS XYZ tiles from `Hosted/NTAD_Noise_2020_CONUS_Aviation_Road_Rail` MapServer (`…/tile/{z}/{y}/{x}`). Screening/trend only, not parcel-precise. See `app/core/bts_noise.py`.

### Building permits near pin (TODO-043, 2026-07-19)

Library risk chip when **high permit activity** is within **~0.25 mi** (402 m). Prefer official city Socrata SODA feeds + `within_circle` — not BuildingEye scrapes. Optional `SOCRATA_APP_TOKEN` (same as crime). Core: `app/core/permits_nearby.py`; cache `data/cache/permits/`.

| Metro | Portal | Dataset ID | Title | Geo for `within_circle` | Lat/Lng fallback | Issue date | Type field | Status field |
|-------|--------|------------|-------|-------------------------|------------------|------------|------------|--------------|
| **Los Angeles** (City of LA / LADBS) | `data.lacity.org` | `pi9x-tg5x` | Building and Safety — Building Permits Issued from 2020 to Present | `geolocation` (Point) | `lat`, `lon` | `issue_date` | `permit_type` | `status_desc` |
| **Seattle** | `data.seattle.gov` | `76t5-zqzr` | Building Permits | `location1` (Location) | `latitude`, `longitude` | `issueddate` | `permittypemapped` (+ `permittypedesc`) | `statuscurrent` |
| **Austin** | `data.austintexas.gov` | `3syk-w9eu` | Issued Construction Permits | `location` (Location) | `latitude`, `longitude` | `issue_date` | `permit_type_desc` | `status_current` |

**Query pattern:** `$where=within_circle(<geo>, <lat>, <lng>, 402) AND <date> >= '<ISO since>'` plus type filters; `$limit` capped; optional `X-App-Token`.

**Type filters (structural / electrical / demolition-ish):**
- **LA:** `permit_type` starts with `Bldg-` or `Nonbldg-`, or equals `Grading` / contains `Demolition`. Dataset is Building-group only (no separate electrical feed in this ID).
- **Seattle:** `permittypemapped` in `Building`, `Demolition`, `Grading` (skip ECA/shoreline exemptions, roof-only noise).
- **Austin:** `permit_type_desc` in `Building Permit`, `Electrical Permit` (skip plumbing / mechanical / driveway volume).

**Status:** exclude withdrawn / canceled / denied / refund; keep Issued / Active / Finaled / Completed — activity is driven by **issue date**, not “still open.”

**High-activity rule (v1):** **≥ 8** matching permits in the **0.25 mi** circle with issue date in the last **24 months**. Tuned for dense urban blocks (a handful of remodel permits should not light the chip; a cluster of new/demo/electrical work should). Documented in module constants; outside supported cities → no chip.

**Persistence:** `Property.permits_activity` (JSON) + `permits_activity_at`; compute on add / post-geocode best-effort; never fail add-home. UI: amber `.hb-nearby-chip--amber` via `chip_spec_for` → `_extra_signal_chips` on library cards + property header; library paint runs `refresh_stale_permits_activity_job`.

**Avoid:** BuildingEye / Accela portal scrapes when SODA works; national permit aggregators; Map overlay of every permit in v1.

### Missing broadband / FCC BDC (TODO-042, 2026-07-19)

Library magenta risk chip when the pin’s census block reports **no fixed terrestrial broadband**. **DSL or cable alone does not flag** — only total absence of fixed terrestrial service. Satellite-only still flags.

**Credentials required:** `FCC_BDC_USERNAME` + `FCC_BDC_HASH` (alias `FCC_BDC_HASH_VALUE`) as HTTP headers `username` / `hash_value`. Register at [broadbandmap.fcc.gov](https://broadbandmap.fcc.gov) → Manage API Access. Missing credentials → status `unknown`, **no chip** (never false-alarm). Soft-pings `GET https://broadbandmap.fcc.gov/api/public/map/listAsOfDates`.

**BDC Public Data API** is bulk-download only (`listAvailabilityData`, `downloadFile`, …). Location Fabric needs a separate CostQuest license.

**Point availability (chosen path when credentials are set)** — `app/core/fcc_broadband.py`:
1. `GET https://geo.fcc.gov/api/census/block/find?latitude=&longitude=&censusYear=2020&format=json` → 15-digit block FIPS.
2. Esri Living Atlas FeatureServer `FCC_Broadband_Data_Collection_December_2024_View` layer **4 (Blocks)** — query `GEOID='…'` for `UniqueProvidersCopper|Cable|Fiber|LTFW|LBRTFW` (URL in module).

Block-level aggregation can overstate coverage vs a specific BSL; adequate for a library screening chip.

**Persistence:** `Property.broadband_status` + `broadband_at`; cache under `data/cache/fcc_broadband/` (~7d); compute on add / post-geocode; stale refresh via `refresh_stale_broadband_status_job`. Helpers folded into `listing_risk_chips`.

### Keys

| Key | Needed? |
|-----|---------|
| `CENSUS_API_KEY` | Yes for live ACS |
| `SOCRATA_APP_TOKEN` | Optional (rate limits) |
| `FCC_BDC_USERNAME` + `FCC_BDC_HASH` | Optional — enables missing-broadband library chip |
| FEMA / Redfin download / NCES / EPA / Living Atlas BDC | No key (Living Atlas used only after BDC credentials opt-in) |

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
- **Quality layer (2026-07-18 — swapped off SchoolDigger, which is paid):** free **California School Dashboard** performance-level color (Blue/Green/Yellow/Orange/Red), looked up by 14-digit CDS code from the free CDE **Academic Indicator** downloadable data (`app/core/school_quality.py`). CDE publishes one Academic Indicator TXT per reporting year at a predictable URL — confirmed by the naming pattern on its ELPI/ELA-participation siblings (`.../researchfiles/cadashboard/elpidownload2022.txt`, `.../elapratedownload2019.txt`): `{indicator}download{year}.txt`, so ELA 2024–25 is `https://www3.cde.ca.gov/researchfiles/cadashboard/eladownload2025.txt`. Record layout (`cde.ca.gov/ta/ac/cm/ela24.asp`, confirmed via search-engine cache since the live page returns a bot-check CAPTCHA from this sandbox): tab-separated, lowercase field names — `cds`, `rtype` (`S`=school/`D`=district/`X`=state), `studentgroup` (`ALL`=All Students, confirmed against a real ELA-participation sample file), `color` (`1`=Red…`5`=Blue, `0`=No Color), `statuslevel` (`1`=Very Low…`5`=Very High). We keep only school-level, All-Students rows with a recognized color as a slim `cds → {color, status, year}` map. **Parent reviews:** a **Niche** K-12 school-search deep link (no scrape) — `niche.com/k12/search/best-schools/?q=...` — plus a direct `caschooldashboard.org/reports/{cds}/{year}` report-page link. No API key of any kind.
- **Cache:** ~7 days under `data/cache/school_zones/` (attendance + name resolve); ~30 days under `data/cache/ca_dashboard/` for the slim CDS→color map (same one-time-download-then-reuse pattern as the Redfin ZIP median tracker, since the source TXT is ~26MB).
- **Concern to verify on a real run:** the ELA TXT URL/field names above are inferred from CDE's own naming convention for sibling files plus a search-engine-cached copy of the record-layout page (live CDE pages return a bot-check CAPTCHA from this sandbox's network) — not fetched and parsed end-to-end here. `lookup_dashboard_status` never raises: if the URL, delimiter, or column names have drifted, the color badge is silently omitted and the Niche/Dashboard links still render. Confirm on a real Windows run and adjust `ELA_DASHBOARD_TXT_URL` / column names in `app/core/school_quality.py` if the download 404s or `parse_dashboard_rows` yields an empty map.
- **Avoid:** paid attendance-zone or ratings APIs (SchoolDigger, SchoolScope — the latter's public API is 403/"coming soon"), GreatSchools API, guessing a "nearest school" as the assigned one (attendance boundaries are not proximity-based).
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
